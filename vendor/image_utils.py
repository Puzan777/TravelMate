import os

from PIL import Image as PILImage, UnidentifiedImageError


DEFAULT_MAX_IMAGES = 10
DEFAULT_MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
DEFAULT_ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
DEFAULT_ALLOWED_IMAGE_CONTENT_TYPES = {
    'image/jpeg',
    'image/png',
    'image/webp',
    'image/gif',
}


def is_valid_uploaded_image(image_file):
    try:
        image_file.seek(0)
        with PILImage.open(image_file) as img:
            img.verify()
        image_file.seek(0)
        with PILImage.open(image_file) as img:
            img.load()
        return True
    except (UnidentifiedImageError, OSError, ValueError):
        return False
    finally:
        try:
            image_file.seek(0)
        except Exception:
            pass


def validate_uploaded_images(
    image_files,
    existing_count,
    *,
    entity_label,
    max_images=DEFAULT_MAX_IMAGES,
    max_size_bytes=DEFAULT_MAX_IMAGE_SIZE,
    allowed_extensions=None,
    allowed_content_types=None,
):
    allowed_extensions = allowed_extensions or DEFAULT_ALLOWED_IMAGE_EXTENSIONS
    allowed_content_types = allowed_content_types or DEFAULT_ALLOWED_IMAGE_CONTENT_TYPES

    if existing_count + len(image_files) > max_images:
        return f'You can upload up to {max_images} images per {entity_label}.'

    for image_file in image_files:
        ext = os.path.splitext(image_file.name)[1].lower()
        if ext not in allowed_extensions:
            return 'Only JPG, JPEG, PNG, WEBP, and GIF files are allowed.'

        if getattr(image_file, 'size', 0) > max_size_bytes:
            return 'Each image must be 5 MB or smaller.'

        content_type = (getattr(image_file, 'content_type', '') or '').lower()
        if content_type and content_type not in allowed_content_types:
            return 'Invalid image type uploaded.'

        if not is_valid_uploaded_image(image_file):
            return 'Uploaded file is not a valid image.'

    return None


def parse_selected_primary_index(raw_value, total_items):
    if raw_value is None:
        return None
    try:
        index = int(raw_value)
    except (TypeError, ValueError):
        return None
    if 0 <= index < total_items:
        return index
    return None


def set_primary_image(images_source, preferred_image_id=None):
    if hasattr(images_source, 'all'):
        images_qs = images_source.all().order_by('created_at')
    else:
        images_qs = images_source.order_by('created_at')

    if not images_qs.exists():
        return

    if preferred_image_id is not None and images_qs.filter(pk=preferred_image_id).exists():
        images_qs.update(is_primary=False)
        images_qs.filter(pk=preferred_image_id).update(is_primary=True)
        return

    if images_qs.filter(is_primary=True).exists():
        return

    first_image = images_qs.first()
    if first_image is not None:
        first_image.is_primary = True
        first_image.save(update_fields=['is_primary'])
