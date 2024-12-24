from rest_framework import serializers
from .models import SParameter, Simulation

class SParameterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SParameter
        fields = ['id', 'name', 'description', 'file', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

class SimulationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Simulation
        fields = ['id', 'status', 'result_file', 'error_message', 
                 'created_at', 'updated_at', 'parameters', 'retry_count'] 