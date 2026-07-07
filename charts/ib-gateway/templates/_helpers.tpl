{{- define "ib-gateway.name" -}}
ib-gateway
{{- end }}

{{- define "ib-gateway.fullname" -}}
{{ include "ib-gateway.name" . }}-{{ .Release.Name }}
{{- end }}
