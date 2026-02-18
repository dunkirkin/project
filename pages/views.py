from django.http import HttpResponse
from django.shortcuts import render

# Create your views here.

# Base home page
def home_view(*args, **kwargs):
    return HttpResponse("<h1>home page</h1>")