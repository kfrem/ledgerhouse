from django import template


register = template.Library()


@register.filter
def get_item(mapping, key):
    if not mapping:
        return None
    return mapping.get(key)


@register.filter
def human_status(value):
    if value is None:
        return ""
    text = str(value).replace("_", " ").replace("-", " ")
    output = []
    previous = ""
    for char in text:
        if previous and char.isupper() and (previous.islower() or previous.isdigit()):
            output.append(" ")
        output.append(char)
        previous = char
    return "".join(output).strip()
