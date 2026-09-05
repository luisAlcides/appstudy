-- Tabla donde AppStudy guarda tu progreso en Supabase.
--
-- Copia el CONTENIDO de este archivo —no su ruta— y pégalo entero en el editor
-- SQL del panel (SQL Editor → New query → Run). Se puede volver a ejecutar
-- tantas veces como quieras: solo crea lo que falte, y nada de lo que hace es
-- destructivo, así que el editor no pregunta antes de correrlo.
--
-- Cada equipo tuyo (portátil, torre…) guarda aquí **una** fila con su snapshot
-- completo: mazos, tarjetas y capítulos propios, estado FSRS, historial de
-- repasos, lecturas y fuentes. La aplicación baja las filas de tus otros
-- equipos, las fusiona en local con el reloj de cada elemento y vuelve a subir
-- la suya. Por eso nadie pisa a nadie y da igual el orden en que enciendas cada
-- equipo.
--
-- La separación entre usuarios la impone Postgres, no la aplicación: la
-- política de abajo ata cada fila a `auth.uid()`, así que aunque dos personas
-- usen el mismo proyecto ninguna puede leer ni escribir las filas de la otra.

create table if not exists public.sync_snapshots (
    user_id     uuid        not null default auth.uid()
                            references auth.users(id) on delete cascade,
    -- El identificador del equipo que genera AppStudy: 32 dígitos hexadecimales.
    device      text        not null check (device ~ '^[a-f0-9]{32}$'),
    datos       jsonb       not null,
    actualizado timestamptz not null default now(),
    primary key (user_id, device)
);

-- Nadie ve nada sin haber entrado, y quien entra solo ve lo suyo.
alter table public.sync_snapshots enable row level security;

-- `create policy` no tiene forma «si no existe», así que se pregunta antes: así
-- volver a ejecutar el script no falla ni hace falta borrar la política.
do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename  = 'sync_snapshots'
          and policyname = 'cada quien lo suyo'
    ) then
        create policy "cada quien lo suyo" on public.sync_snapshots
            for all
            to authenticated
            using (auth.uid() = user_id)
            with check (auth.uid() = user_id);
    end if;
end
$$;

-- `default now()` solo actúa al insertar; al reemplazar el snapshot de un
-- equipo hace falta esto para que la fecha diga la verdad.
create or replace function public.sync_snapshots_touch()
returns trigger
language plpgsql
as $$
begin
    new.actualizado := now();
    new.user_id := old.user_id;   -- la fila no cambia de dueño
    return new;
end;
$$;

create or replace trigger sync_snapshots_touch
    before update on public.sync_snapshots
    for each row execute function public.sync_snapshots_touch();

-- Para ver de un vistazo qué equipos tienes y cuándo sincronizó cada uno,
-- sin descargarte los snapshots enteros:
--
--   select device, actualizado, pg_size_pretty(length(datos::text)::bigint) as peso
--   from public.sync_snapshots order by actualizado desc;
