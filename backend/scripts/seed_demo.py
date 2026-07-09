"""Seed a demo project end-to-end for manual verification.

Run with:  python manage.py shell < scripts/seed_demo.py
"""

from pathlib import Path

import numpy as np
import tifffile
from django.conf import settings
from django.contrib.auth.models import User

from accounts.models import AnnotatorProfile
from core.choices import LabelType
from projects.services import create_project
from volumes.services import register_volume

# --- users -----------------------------------------------------------------
manager, _ = User.objects.get_or_create(
    username="manager", defaults={"is_staff": True, "is_superuser": True}
)
manager.set_password("demo12345")
manager.save()

annotator, _ = User.objects.get_or_create(username="alice")
annotator.set_password("demo12345")
annotator.save()
AnnotatorProfile.objects.get_or_create(
    user=annotator,
    defaults={"is_active_annotator": True, "max_active_tasks": 10,
              "pay_rate_per_task": "2.50"},
)

# --- a real TIFF volume under MITO_DATA_ROOT (to exercise autodetect) ------
root = Path(settings.MITO_DATA_ROOT)
root.mkdir(parents=True, exist_ok=True)
img_path = root / "demo_volume.tiff"
if not img_path.exists():
    tifffile.imwrite(str(img_path), np.zeros((48, 128, 96), dtype=np.uint8))

project = create_project(
    title="Demo mitochondria project", created_by=manager,
    description="Seeded demo.",
)
volume = register_volume(
    project=project, name="demo_volume", image_path="demo_volume.tiff",
    label_type=LabelType.NONE,
)

print("PROJECT_ID", project.id)
print("VOLUME_ID", volume.id)
print("VOLUME_SHAPE", volume.shape_x, volume.shape_y, volume.shape_z)
