{{/*
Expand the name of the chart.
*/}}
{{- define "openmu.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "openmu.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Chart label.
*/}}
{{- define "openmu.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "openmu.labels" -}}
helm.sh/chart: {{ include "openmu.chart" . }}
{{ include "openmu.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: openmu-saas
openmu.saas/server-name: {{ .Values.serverName | quote }}
{{- end }}

{{- define "openmu.selectorLabels" -}}
app.kubernetes.io/name: {{ include "openmu.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "openmu.postgresSelectorLabels" -}}
{{ include "openmu.selectorLabels" . }}
app.kubernetes.io/component: postgres
{{- end }}

{{- define "openmu.openmuSelectorLabels" -}}
{{ include "openmu.selectorLabels" . }}
app.kubernetes.io/component: openmu
{{- end }}

{{- define "openmu.namespace" -}}
{{- default .Release.Namespace .Values.namespace.name }}
{{- end }}

{{- define "openmu.postgresName" -}}
{{- printf "%s-postgres" (include "openmu.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "openmu.postgresSecretName" -}}
{{- printf "%s-postgres" (include "openmu.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "openmu.adminSecretName" -}}
{{- printf "%s-admin" (include "openmu.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "openmu.configMapName" -}}
{{- printf "%s-config" (include "openmu.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "openmu.adminKeysPvcName" -}}
{{- printf "%s-admin-keys" (include "openmu.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
hostPort is only valid with replicaCount: 1 (one pod can bind the node ports).
*/}}
{{- define "openmu.gamePorts" -}}
{{- .Values.ports.game | toJson }}
{{- end }}
