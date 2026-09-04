"""Settings and custom-template persistence interface."""

from app.persistence import storage_backend

get_settings = storage_backend.get_settings
save_settings = storage_backend.save_settings
list_templates = storage_backend.list_templates
get_template = storage_backend.get_template
active_template_count = storage_backend.active_template_count
create_template = storage_backend.create_template
activate_legacy_template = storage_backend.activate_legacy_template
update_template = storage_backend.update_template
rename_template = storage_backend.rename_template
delete_template = storage_backend.delete_template
save_template_selection = storage_backend.save_template_selection
