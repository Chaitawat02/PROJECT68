from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Create a sample SilkPattern entry (for testing AR pages)'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Create even if records exist')
        parser.add_argument('--siid', type=str, default='SAMPLE001', help='Si_ID value')

    def handle(self, *args, **options):
        from main.models import SilkPattern

        if SilkPattern.objects.exists() and not options['force']:
            self.stdout.write(self.style.WARNING('SilkPattern exists. Use --force to create another.'))
            for s in SilkPattern.objects.all()[:10]:
                self.stdout.write(f'{s.pk}: {s.Si_ID} - {s.Si_name}')
            return

        s = SilkPattern.objects.create(
            Si_ID=options['siid'],
            Si_name='ตัวอย่างผ้าไหม AR',
            Si_address='จังหวัดตัวอย่าง',
            Si_type='ยกดอก',
            Si_color='แดง',
            Si_history='ตัวอย่างข้อมูลแหล่งที่มาและวิธีการทอสำหรับการทดสอบฟีเจอร์ AR'
        )

        self.stdout.write(self.style.SUCCESS(f'Created SilkPattern pk={s.pk} Si_ID={s.Si_ID}'))
