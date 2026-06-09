"""python manage.py copiar_temporada --origen 2026 --destino 2027"""
from django.core.management.base import BaseCommand, CommandError
from vinos.models import Temporada, Vino, Configuracion


class Command(BaseCommand):
    help = 'Copia configuraciones de una temporada a otra como punto de partida'

    def add_arguments(self, parser):
        parser.add_argument('--origen', type=int, required=True)
        parser.add_argument('--destino', type=int, required=True)
        parser.add_argument('--forzar', action='store_true')
        parser.add_argument('--solo-vigentes', action='store_true')

    def handle(self, *args, **options):
        try:
            temp_origen = Temporada.objects.get(anio=options['origen'])
        except Temporada.DoesNotExist:
            raise CommandError(f"No existe la temporada {options['origen']}")

        temp_destino, created = Temporada.objects.get_or_create(
            anio=options['destino'],
            defaults={'descripcion': f"Copiado desde {options['origen']}"}
        )
        if created:
            self.stdout.write(f'Temporada {options["destino"]} creada.')

        qs = Configuracion.objects.filter(temporada=temp_origen).select_related('vino', 'material')
        if options['solo_vigentes']:
            qs = qs.filter(vino__estado='vigente', vino__estado_mezcla='vigente')

        por_vino = {}
        for c in qs:
            por_vino.setdefault(c.vino.codigo, []).append(c)

        con_destino = set(
            Configuracion.objects.filter(temporada=temp_destino)
            .values_list('vino__codigo', flat=True).distinct()
        )

        copiados = saltados = total = 0
        for cod, configs in por_vino.items():
            if cod in con_destino and not options['forzar']:
                saltados += 1
                continue
            if options['forzar'] and cod in con_destino:
                Configuracion.objects.filter(vino__codigo=cod, temporada=temp_destino).delete()
            Configuracion.objects.bulk_create([
                Configuracion(vino=c.vino, temporada=temp_destino,
                              material=c.material, participacion=c.participacion)
                for c in configs
            ], ignore_conflicts=True)
            copiados += 1
            total += len(configs)

        Vino.objects.all().update(revision='pendiente')

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Copia completa:\n'
            f'  Vinos copiados:  {copiados}\n'
            f'  Componentes:     {total}\n'
            f'  Saltados:        {saltados}\n'
            f'\nSelecciona {options["destino"]} como temporada activa '
            f'y {options["origen"]} como referencia en la app.'
        ))
