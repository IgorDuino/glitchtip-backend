import re

from django import template
from django.conf import settings
from django.template.defaultfilters import stringfilter

register = template.Library()


@register.simple_tag()
def get_domain():
    return settings.GLITCHTIP_URL.geturl()


@register.filter()
@stringfilter
def stripurlchars(string):
    stripped_text = re.sub(r"\.com|http|\/|\.|\:|\$", "", string)
    return stripped_text[:60]
