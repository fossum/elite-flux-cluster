{{- define "development-workspace.name" -}}
development-workspace
{{- end }}

{{- define "development-workspace.fullname" -}}
{{ include "development-workspace.name" . }}-{{ .Release.Name }}
{{- end }}
