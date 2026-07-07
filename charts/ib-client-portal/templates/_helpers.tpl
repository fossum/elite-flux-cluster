{{- define "ib-client-portal.name" -}}
ib-client-portal
{{- end }}

{{- define "ib-client-portal.fullname" -}}
{{ include "ib-client-portal.name" . }}-{{ .Release.Name }}
{{- end }}
