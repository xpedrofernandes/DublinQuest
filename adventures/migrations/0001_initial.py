import django.contrib.gis.db.models.fields
import django.core.validators
import django.db.models.deletion
import places.validators
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('places', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Adventure',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('owner_uuid', models.UUIDField(db_index=True, editable=False)),
                ('title', models.CharField(max_length=120)),
                ('start', django.contrib.gis.db.models.fields.PointField(srid=2157, validators=[places.validators.validate_geometry])),
                ('radius_m', models.PositiveIntegerField(default=2000, validators=[django.core.validators.MinValueValidator(250), django.core.validators.MaxValueValidator(5000)])),
                ('categories', models.JSONField(default=list)),
                ('requested_stops', models.PositiveSmallIntegerField(default=5, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10)])),
                ('search_area', django.contrib.gis.db.models.fields.PolygonField(blank=True, null=True, srid=2157, validators=[places.validators.validate_geometry])),
                ('path', django.contrib.gis.db.models.fields.LineStringField(blank=True, null=True, srid=2157, validators=[places.validators.validate_geometry])),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
                'constraints': [models.CheckConstraint(condition=models.Q(('radius_m__gte', 250), ('radius_m__lte', 5000)), name='adventure_radius_range'), models.CheckConstraint(condition=models.Q(('requested_stops__gte', 1), ('requested_stops__lte', 10)), name='adventure_stop_count_range')],
            },
        ),
        migrations.CreateModel(
            name='AdventureStop',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('distance_from_start_m', models.FloatField(validators=[django.core.validators.MinValueValidator(0)])),
                ('distance_from_previous_m', models.FloatField(validators=[django.core.validators.MinValueValidator(0)])),
                ('visited_at', models.DateTimeField(blank=True, null=True)),
                ('adventure', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stops', to='adventures.adventure')),
                ('place', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='adventure_stops', to='places.place')),
            ],
            options={
                'ordering': ['position'],
                'constraints': [models.UniqueConstraint(fields=('adventure', 'position'), name='stop_position_unique'), models.UniqueConstraint(fields=('adventure', 'place'), name='stop_place_unique'), models.CheckConstraint(condition=models.Q(('position__gte', 1)), name='stop_position_positive'), models.CheckConstraint(condition=models.Q(('distance_from_previous_m__gte', 0), ('distance_from_start_m__gte', 0)), name='stop_distances_nonnegative')],
            },
        ),
    ]
