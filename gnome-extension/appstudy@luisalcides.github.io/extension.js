/* AppStudy en la barra superior de GNOME.
 *
 * La extensión no toca la base de datos: le pregunta al propio programa con
 * `appstudy --status`, que responde un JSON en milisegundos porque ni siquiera
 * carga GTK. Así el indicador nunca se queda con datos viejos ni bloquea el
 * shell.
 */
import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const REFRESCO = 60;               // segundos entre consultas

/** Dónde está el comando: en el PATH o en ~/.local/bin, que es donde lo deja install.sh. */
function comando() {
    return GLib.find_program_in_path('appstudy')
        ?? GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'appstudy']);
}

/** Lanza appstudy con argumentos y se desentiende. */
function lanzar(args) {
    try {
        const proc = Gio.Subprocess.new([comando(), ...args],
            Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);
        proc.wait_async(null, null);
    } catch (e) {
        Main.notifyError('AppStudy', `No pude ejecutar ${comando()}: ${e.message}`);
    }
}

/** Pregunta algo a appstudy y devuelve el JSON ya convertido (o null si falló). */
function consultar(args, cb) {
    let proc;
    try {
        proc = Gio.Subprocess.new([comando(), ...args],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE);
    } catch (e) {
        cb(null);
        return;
    }
    proc.communicate_utf8_async(null, null, (p, res) => {
        try {
            const [, salida] = p.communicate_utf8_finish(res);
            cb(JSON.parse(salida));
        } catch (e) {
            cb(null);
        }
    });
}

/** Un número grande con su etiqueta debajo. */
const Dato = GObject.registerClass(
class Dato extends St.BoxLayout {
    _init(etiqueta) {
        super._init({vertical: true, style_class: 'appstudy-stat', x_expand: true});
        this._valor = new St.Label({
            text: '–', style_class: 'appstudy-stat-value',
            x_align: Clutter.ActorAlign.CENTER,
        });
        this.add_child(this._valor);
        this.add_child(new St.Label({
            text: etiqueta, style_class: 'appstudy-stat-label',
            x_align: Clutter.ActorAlign.CENTER,
        }));
    }

    set(valor) {
        this._valor.text = String(valor);
    }
});

const Indicador = GObject.registerClass(
class Indicador extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'AppStudy');

        const caja = new St.BoxLayout({style_class: 'appstudy-indicator'});
        this._icono = new St.Icon({
            icon_name: 'accessories-dictionary-symbolic',
            style_class: 'system-status-icon',
        });
        this._cuenta = new St.Label({
            text: '', style_class: 'appstudy-count',
            y_align: Clutter.ActorAlign.CENTER,
        });
        caja.add_child(this._icono);
        caja.add_child(this._cuenta);
        this.add_child(caja);

        this._construirMenu();

        // Al abrir el menú siempre se ven datos frescos
        this.menu.connect('open-state-changed', (_m, abierto) => {
            if (abierto)
                this.refrescar();
        });
    }

    _construirMenu() {
        // -- los cuatro números
        const fila = new PopupMenu.PopupBaseMenuItem({
            reactive: false, can_focus: false, style_class: 'appstudy-stats',
        });
        const caja = new St.BoxLayout({x_expand: true, style_class: 'appstudy-stats'});
        this._pendientes = new Dato('PENDIENTES');
        this._hoy = new Dato('HOY');
        this._racha = new Dato('RACHA');
        this._dominadas = new Dato('DOMINADAS');
        for (const d of [this._pendientes, this._hoy, this._racha, this._dominadas])
            caja.add_child(d);
        fila.add_child(caja);
        this.menu.addMenuItem(fila);

        this._proximo = new PopupMenu.PopupMenuItem('', {reactive: false, can_focus: false});
        this._proximo.label.add_style_class_name('appstudy-quote-by');
        this.menu.addMenuItem(this._proximo);

        // -- la frase del rato
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._cita = new St.Label({text: '', style_class: 'appstudy-quote'});
        this._cita.clutter_text.line_wrap = true;
        this._citaAutor = new St.Label({text: '', style_class: 'appstudy-quote-by'});
        this._citaAutor.clutter_text.line_wrap = true;
        const bloque = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        const columna = new St.BoxLayout({vertical: true, x_expand: true});
        columna.add_child(this._cita);
        columna.add_child(this._citaAutor);
        bloque.add_child(columna);
        this.menu.addMenuItem(bloque);

        // -- acciones
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._accion('Estudiar ahora', () => lanzar(['--popup']));
        this._accion('Abrir AppStudy', () => lanzar([]));

        this._mascota = new PopupMenu.PopupSwitchMenuItem('Bit en el escritorio', false);
        this._mascota.connect('toggled', (_i, activo) => {
            if (activo)
                lanzar(['--pet']);
            else
                consultar(['--pet-off'], () => {});
            // Al proceso le cuesta un momento arrancar o irse
            GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {
                this.refrescar();
                return GLib.SOURCE_REMOVE;
            });
        });
        this.menu.addMenuItem(this._mascota);
    }

    _accion(texto, cb) {
        const item = new PopupMenu.PopupMenuItem(texto);
        item.connect('activate', () => {
            this.menu.close();
            cb();
        });
        this.menu.addMenuItem(item);
    }

    refrescar() {
        consultar(['--status'], datos => this._pintar(datos));
    }

    _pintar(d) {
        if (!d) {
            this._cuenta.text = '?';
            this._cita.text = 'No encuentro el comando «appstudy». Ejecuta install.sh.';
            this._citaAutor.text = '';
            return;
        }
        const debidas = d.pendientes + d.nuevas;
        this._cuenta.text = debidas > 0 ? String(debidas) : '';
        if (debidas > 0)
            this._cuenta.add_style_class_name('appstudy-due');
        else
            this._cuenta.remove_style_class_name('appstudy-due');

        this._pendientes.set(d.pendientes);
        this._hoy.set(d.hoy);
        this._racha.set(`${d.racha} d`);
        this._dominadas.set(d.dominadas);
        this._proximo.label.text = debidas > 0
            ? `${d.nuevas} sin estrenar · ${d.total} tarjetas en total`
            : (d.proximo ? `Todo al día. La siguiente, en ${d.proximo}.` : 'Todo al día.');

        if (d.cita) {
            this._cita.text = `«${d.cita.frase}»`;
            this._citaAutor.text = `— ${d.cita.autor}, ${d.cita.obra}`;
        }
        this._mascota.setToggleState(!!d.mascota);
    }
});

export default class AppStudyExtension extends Extension {
    enable() {
        this._indicador = new Indicador();
        Main.panel.addToStatusArea(this.uuid, this._indicador, 0, 'right');
        this._indicador.refrescar();
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, REFRESCO, () => {
            this._indicador.refrescar();
            return GLib.SOURCE_CONTINUE;
        });
    }

    disable() {
        if (this._timer) {
            GLib.Source.remove(this._timer);
            this._timer = null;
        }
        this._indicador?.destroy();
        this._indicador = null;
    }
}
