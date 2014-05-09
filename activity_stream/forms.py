from django import forms
from django.forms.widgets import CheckboxSelectMultiple
from models import Stream, StreamConnection, StreamItem
from broker.models import Connection


class StreamForm(forms.ModelForm):
    streamconnections = forms.ModelMultipleChoiceField(widget=CheckboxSelectMultiple,
                                                       queryset=StreamConnection.objects.all(),
                                                       label='Stream Connections'
                                                       )

    class Meta:
        model = Stream
        fields = ['streamconnections']