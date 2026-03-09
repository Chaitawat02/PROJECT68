from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0029_bookingquestionresponse_submission_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='question',
            name='category',
            field=models.CharField(choices=[('museum', 'ภาพรวมพิพิธภัณฑ์'), ('silk', 'ผ้าไหม'), ('speaker', 'วิทยากร')], db_index=True, default='museum', max_length=20, verbose_name='หมวดคำถาม'),
        ),
    ]
