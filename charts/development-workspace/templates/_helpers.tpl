{{- define "development-workspace.name" -}}
development-workspace
{{- end }}

{{- define "development-workspace.fullname" -}}
{{ include "development-workspace.name" . }}-{{ .Release.Name }}
{{- end }}

{{- define "development-workspace.restarterName" -}}
{{ printf "%s-restarter" (include "development-workspace.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "development-workspace.restarterCronJobName" -}}
{{ printf "%s-restarter" (include "development-workspace.fullname" .) | trunc 52 | trimSuffix "-" }}
{{- end }}
