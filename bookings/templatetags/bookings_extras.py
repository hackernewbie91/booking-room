from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Mengembalikan nilai dictionary[key] dengan aman."""
    if dictionary is None:
        return None
    if not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)
