from django.conf.urls import url
from django.urls import path

from . import views

urlpatterns = [
    url(r'^(?P<url>.*)$', views.index, name='index'),
]