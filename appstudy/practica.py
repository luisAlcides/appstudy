"""Casos guiados y progreso local; independiente de GTK y de la IA."""
import json
import re
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

from . import db


def catalogo():
    return json.loads((Path(__file__).parent / "data" / "practicas.json").read_text(encoding="utf-8"))


def numero(texto):
    """Acepta decimales y fracciones, sin ejecutar expresiones del usuario."""
    if not isinstance(texto, str) or len(texto) > 100:
        raise ValueError("Escribe un número o una fracción, por ejemplo 2,5 o 5/2.")
    patron = r"[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)"
    partes = texto.strip().replace("−", "-").split("/")
    if len(partes) > 2 or any(not re.fullmatch(patron, p.strip()) for p in partes):
        raise ValueError("Escribe un número o una fracción, por ejemplo 2,5 o 5/2.")
    try:
        with localcontext() as contexto:
            contexto.prec = 110
            valores = [Decimal(p.strip().replace(",", ".")) for p in partes]
            if len(valores) == 2 and valores[1] == 0:
                raise ValueError("El denominador no puede ser cero.")
            return valores[0] if len(valores) == 1 else valores[0] / valores[1]
    except InvalidOperation as exc:
        raise ValueError("No se pudo interpretar el número.") from exc


def es_correcta(paso, respuesta):
    if paso.get("tipo") == "numero":
        valor = numero(respuesta)
        return abs(valor - numero(paso["respuesta"])) <= Decimal(paso.get("tolerancia", "0.000000001"))
    if type(respuesta) is not int or not 0 <= respuesta < len(paso["opciones"]):
        raise ValueError("Opción inválida")
    return respuesta == paso["correcta"]


class SesionPractica:
    def __init__(self, con, caso):
        self.con, self.caso = con, caso
        self.clave = "practica_v1_" + caso["id"]
        try:
            estado = json.loads(db.get_meta(con, self.clave, "[]"))
        except (ValueError, TypeError):
            estado = []
        self.estado = []
        if isinstance(estado, list):
            for paso, dato in zip(caso["pasos"], estado):
                if not isinstance(dato, dict):
                    break
                intentos = dato.get("intentos")
                pistas = dato.get("pistas")
                resuelto = dato.get("resuelto")
                try:
                    resultados = [es_correcta(paso, i) for i in intentos] if isinstance(intentos, list) else []
                except (ValueError, TypeError):
                    break
                if (not isinstance(intentos, list)
                        or type(pistas) is not int or not 0 <= pistas <= len(paso["pistas"])
                        or type(resuelto) is not bool
                        or resuelto != bool(resultados and resultados[-1])
                        or any(resultados[:-1])):
                    break
                self.estado.append({"intentos": intentos, "pistas": pistas, "resuelto": resuelto})
                if not resuelto:
                    break

    @property
    def indice(self):
        return sum(d["resuelto"] for d in self.estado)

    @property
    def terminada(self):
        return self.indice == len(self.caso["pasos"])

    def dato(self):
        if self.terminada:
            raise ValueError("El ejercicio ya terminó")
        if len(self.estado) == self.indice:
            self.estado.append({"intentos": [], "pistas": 0, "resuelto": False})
        return self.estado[self.indice]

    def guardar(self):
        db.set_meta(self.con, self.clave, json.dumps(self.estado))

    def responder(self, opcion):
        dato = self.dato()
        paso = self.caso["pasos"][self.indice]
        correcto = es_correcta(paso, opcion)
        dato["intentos"].append(opcion)
        dato["resuelto"] = correcto
        self.guardar()
        return dato["resuelto"]

    def pista(self):
        dato = self.dato()
        pistas = self.caso["pasos"][self.indice]["pistas"]
        dato["pistas"] = min(len(pistas), dato["pistas"] + 1)
        self.guardar()
        return pistas[:dato["pistas"]]

    def reiniciar(self):
        self.estado = []
        self.guardar()

    def resumen(self):
        return {
            "resueltos": self.indice,
            "sin_ayuda": sum(d["resuelto"] and len(d["intentos"]) == 1 and d["pistas"] == 0
                             for d in self.estado),
            "pistas": sum(d["pistas"] for d in self.estado),
        }
