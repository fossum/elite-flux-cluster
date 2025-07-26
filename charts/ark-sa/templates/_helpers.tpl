{{- define "ark-server.name" -}}
ark-server
{{- end }}

{{- define "ark-server.fullname" -}}
{{ include "ark-server.name" . }}-{{ .Release.Name }}
{{- end }}
