<template>
  <main class="workspace">
    <section class="main-grid">
      <MaterialInputPanel />
      <PlatformResultColumns />
    </section>

    <GenerationHistoryPanel />

    <section class="support-grid">
      <CompliancePanel />
      <BatchJobPanel />
      <ImageWorkflowPanel />
      <ObservabilityPanel />
    </section>

    <TaskHistoryPanel />
  </main>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from "vue";

const BatchJobPanel = defineAsyncComponent(() => import("@/components/BatchJobPanel.vue"));
const CompliancePanel = defineAsyncComponent(() => import("@/components/CompliancePanel.vue"));
const GenerationHistoryPanel = defineAsyncComponent(() => import("@/components/GenerationHistoryPanel.vue"));
const ImageWorkflowPanel = defineAsyncComponent(() => import("@/components/ImageWorkflowPanel.vue"));
const MaterialInputPanel = defineAsyncComponent(() => import("@/components/MaterialInputPanel.vue"));
const ObservabilityPanel = defineAsyncComponent(() => import("@/components/ObservabilityPanel.vue"));
const PlatformResultColumns = defineAsyncComponent(() => import("@/components/PlatformResultColumns.vue"));
const TaskHistoryPanel = defineAsyncComponent(() => import("@/components/TaskHistoryPanel.vue"));
</script>
