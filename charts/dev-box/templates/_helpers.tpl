{{- define "dev-box.name" -}}
dev-box
{{- end }}

{{- define "dev-box.fullname" -}}
{{ include "dev-box.name" . }}-{{ .Release.Name }}
{{- end }}
