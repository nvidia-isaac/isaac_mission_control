{{/*
Expand the name of the chart.
*/}}
{{- define "mission-control.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "mission-control.fullname" -}}
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
Create chart name and version as used by the chart label.
*/}}
{{- define "mission-control.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Main labels
*/}}
{{- define "mission-control.labels" -}}
helm.sh/chart: {{ include "mission-control.chart" . }}
{{ include "mission-control.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Main Selector labels
*/}}
{{- define "mission-control.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mission-control.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
cuOpt labels
*/}}
{{- define "mission-control.cuopt.labels" -}}
helm.sh/chart: {{ include "mission-control.chart" . }}
{{ include "mission-control.cuopt.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
cuOpt Selector labels
*/}}
{{- define "mission-control.cuopt.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mission-control.name" . }}-cuopt
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
waypointGraphGenerator labels
*/}}
{{- define "mission-control.waypointGraphGenerator.labels" -}}
helm.sh/chart: {{ include "mission-control.chart" . }}
{{ include "mission-control.waypointGraphGenerator.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
waypointGraphGenerator Selector labels
*/}}
{{- define "mission-control.waypointGraphGenerator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mission-control.name" . }}-wpg
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "mission-control.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "mission-control.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
