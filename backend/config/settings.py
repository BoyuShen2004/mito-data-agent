"""
Django settings for the Mito Data Agent project.

Mito Data Agent is a web application for managing mitochondria annotation work:
projects, image volumes, frame-based annotation tasks, submissions, review, and
workload tracking. Annotation work is unpaid; there is no payment tracking.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from a local .env file at the repo root if present.
load_dotenv(BASE_DIR.parent / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# --- Core security / debug -------------------------------------------------

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-)xbnet#ko+0&(934o5j80-fr@w*v4pk6ctrap2fyn1tj412q(e",
)

DEBUG = _env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]


# --- Application definition ------------------------------------------------

INSTALLED_APPS = [
    # Manager Admin site (replaces the default django.contrib.admin site).
    "core.admin_apps.ManagerAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    # Local apps
    "core",
    "accounts",
    "projects",
    "volumes",
    "annotation",
    "processing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Database --------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# --- Password validation ---------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Internationalization --------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# --- Static & media files --------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Authentication --------------------------------------------------------

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"


# --- Mito Data Agent settings ----------------------------------------------

# Root directory on the HPC / server / lab machine where image volumes,
# optional labels, submissions, and generated task files live. The database
# stores paths relative to this root, not the large image data itself.
#
# A relative MITO_DATA_ROOT is resolved against the repository root (the parent
# of ``backend/``), so values like ``./data`` mean the same thing regardless of
# the process's current working directory. The default lives inside the repo.
_mito_data_root_env = os.getenv("MITO_DATA_ROOT")
if _mito_data_root_env:
    _mito_data_root = Path(_mito_data_root_env)
    if not _mito_data_root.is_absolute():
        _mito_data_root = BASE_DIR.parent / _mito_data_root
else:
    _mito_data_root = BASE_DIR / "mito_data_root"
MITO_DATA_ROOT = _mito_data_root.resolve()

# Allowed file extensions for uploaded/registered label files (basic QC).
MITO_ALLOWED_LABEL_EXTENSIONS = [
    ".tif",
    ".tiff",
    ".h5",
    ".hdf5",
    ".zarr",
    ".npy",
    ".nii",
    ".nii.gz",
]

# Default frame step used when splitting a volume into tasks.
MITO_DEFAULT_Z_STEP = int(os.getenv("MITO_DEFAULT_Z_STEP", "16"))


# --- Modular provider selection --------------------------------------------
# Each replaceable integration is chosen by name here; the domain services call
# the provider registry, never a low-level adapter directly. See progress/codemap.md
# for the folder that owns each provider.
MITO_QC_PROVIDER = os.getenv("MITO_QC_PROVIDER", "basic")
MITO_PROOFREADING_PROVIDER = os.getenv("MITO_PROOFREADING_PROVIDER", "inapp")
MITO_VISUALIZATION_PROVIDER = os.getenv("MITO_VISUALIZATION_PROVIDER", "inapp")
MITO_PUBLISHING_PROVIDER = os.getenv("MITO_PUBLISHING_PROVIDER", "placeholder")

# SAM2 fork-aware tracking. "local" is a dependency-free CPU stand-in (dev/CI);
# "sam2" runs the real GPU model on an HPC compute node (dispatched via the
# processing backend). The sam2 paths are only read on GPU nodes.
#
# Defaults point at vendor/sam2/ — a full copy of facebookresearch/sam2 plus
# downloaded checkpoints living under this repo's own root (see
# vendor/README.md) — so MITO_TRACKING_PROVIDER=sam2 works with zero .env
# configuration on any machine that has this repo checked out (still needs
# torch + a GPU to actually run; see requirements-sam2.txt and
# progress/development.md). Override via .env if you keep the checkout elsewhere.
MITO_TRACKING_PROVIDER = os.getenv("MITO_TRACKING_PROVIDER", "local")
_default_sam2_root = BASE_DIR.parent / "vendor" / "sam2"
MITO_SAM2_ROOT = os.getenv("MITO_SAM2_ROOT", str(_default_sam2_root))
MITO_SAM2_CHECKPOINT = os.getenv(
    "MITO_SAM2_CHECKPOINT", str(_default_sam2_root / "checkpoints" / "sam2.1_hiera_tiny.pt")
)
MITO_SAM2_CONFIG = os.getenv("MITO_SAM2_CONFIG", "configs/sam2.1/sam2.1_hiera_t.yaml")

# Cellable-ported interactive AI-mask tools (Point Mask / Box Mask / Boundary
# — see backend/annotation/cellable_port/). Unlike vendor/sam2/ above, this
# does NOT vendor (copy) the ~141MB of EfficientSAM ONNX weight files into
# this repo — they're plain data files, not a code dependency, and Cellable
# is a sibling app on the same filesystem (not an external upstream release),
# so the default just points at its already-downloaded copy directly.
# Override MITO_CELLABLE_MODELS_ROOT in .env if that checkout moves or you
# copy the weights somewhere this app owns. onnxruntime/scikit-image/scipy
# are optional deps (requirements-cellable-ai.txt) — see
# cellable_port/ai/registry.py for the graceful "unavailable" degradation
# when they (or the model files) aren't present.
#
# "vits" ("EfficientSam (accuracy)") matches Cellable's own default combo
# (efficient_sam_vits_{encoder,decoder}.onnx) — same model, same weight
# tier, so a click on the same slice should produce the same mask (modulo
# the image-preprocessing alignment in cellable_port/ai/normalize.py). A
# prior round defaulted to "vitt" (tiny/fast) as a CPU-friendliness
# shortcut; per progress/history/21-cellable-parity-followups.md that is
# NOT what "Cellable parity" means to this app's user — mask *identity*
# with local Cellable matters more than raw speed. Set
# MITO_EFFICIENT_SAM_VARIANT=vitt yourself if you explicitly want the
# faster/smaller model instead.
MITO_CELLABLE_MODELS_ROOT = os.getenv(
    "MITO_CELLABLE_MODELS_ROOT",
    "/projects/weilab/shenb/cellable/labelme/models",
)
MITO_EFFICIENT_SAM_VARIANT = os.getenv("MITO_EFFICIENT_SAM_VARIANT", "vits")

# Processing/HPC backend for ProcessingJob execution ("local" or "slurm").
MITO_PROCESSING_BACKEND = os.getenv("MITO_PROCESSING_BACKEND", "local")

# Shared storage root for processing inputs/outputs/logs. Defaults to the data
# root so local development works without extra configuration.
MITO_SHARED_STORAGE_ROOT = os.getenv("MITO_SHARED_STORAGE_ROOT", str(MITO_DATA_ROOT))

# Optional external tool URLs used by the placeholder proofreading/visualization
# providers. Left blank means "not configured".
MITO_PROOFREADING_TOOL_URL = os.getenv("MITO_PROOFREADING_TOOL_URL", "")
MITO_NEUROGLANCER_BASE_URL = os.getenv("MITO_NEUROGLANCER_BASE_URL", "")

# --- SLURM adapter configuration (all lab-specific values come from env) ----
MITO_SLURM_PARTITION = os.getenv("MITO_SLURM_PARTITION", "")
MITO_SLURM_ACCOUNT = os.getenv("MITO_SLURM_ACCOUNT", "")
MITO_SLURM_SBATCH = os.getenv("MITO_SLURM_SBATCH", "sbatch")
MITO_SLURM_SQUEUE = os.getenv("MITO_SLURM_SQUEUE", "squeue")
MITO_SLURM_SACCT = os.getenv("MITO_SLURM_SACCT", "sacct")
MITO_SLURM_SCANCEL = os.getenv("MITO_SLURM_SCANCEL", "scancel")


# --- Django REST Framework -------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": None,
}


# --- CORS (React dev server) ----------------------------------------------

CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "DJANGO_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True
