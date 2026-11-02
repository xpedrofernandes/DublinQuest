import django.contrib.gis.db.models.fields
import django.core.validators
import django.db.models.deletion
import places.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='DatasetSource',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(unique=True)),
                ('title', models.CharField(max_length=255)),
                ('publisher', models.CharField(max_length=255)),
                ('resource_url', models.URLField(max_length=1000)),
                ('licence_name', models.CharField(max_length=255)),
                ('licence_url', models.URLField(max_length=1000)),
                ('attribution', models.TextField()),
                ('snapshot_filename', models.CharField(max_length=255)),
                ('sha256', models.CharField(max_length=64, validators=[django.core.validators.RegexValidator('\\A[0-9a-f]{64}\\Z')])),
            ],
        ),
        migrations.CreateModel(
            name='Park',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_key', models.CharField(max_length=100)),
                ('name', models.CharField(max_length=255)),
                ('typology', models.CharField(blank=True, max_length=100)),
                ('boundary', django.contrib.gis.db.models.fields.MultiPolygonField(srid=2157, validators=[places.validators.validate_geometry])),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='places.datasetsource')),
            ],
            options={
                'ordering': ['name', 'pk'],
            },
        ),
        migrations.CreateModel(
            name='Place',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_key', models.CharField(max_length=100)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('category', models.CharField(choices=[('street_art', 'Street art'), ('public_art', 'Public art and memorials'), ('heritage', 'Heritage and landmarks'), ('park', 'Parks')], db_index=True, max_length=20)),
                ('point', django.contrib.gis.db.models.fields.PointField(srid=2157, validators=[places.validators.validate_geometry])),
                ('artist', models.CharField(blank=True, max_length=255)),
                ('profile_url', models.URLField(blank=True, max_length=1000)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('park', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='place', to='places.park')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='places.datasetsource')),
            ],
            options={
                'ordering': ['name', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='park',
            constraint=models.UniqueConstraint(fields=('source', 'source_key'), name='park_source_key_unique'),
        ),
        migrations.AddConstraint(
            model_name='place',
            constraint=models.UniqueConstraint(fields=('source', 'source_key'), name='place_source_key_unique'),
        ),
        migrations.AddConstraint(
            model_name='place',
            constraint=models.CheckConstraint(condition=models.Q(('category__in', ['street_art', 'public_art', 'heritage', 'park'])), name='place_category_valid'),
        ),
        migrations.AddConstraint(
            model_name='place',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('category', 'park'), ('park__isnull', False)), models.Q(models.Q(('category', 'park'), _negated=True), ('park__isnull', True)), _connector='OR'), name='place_park_category_consistent'),
        ),
    ]
