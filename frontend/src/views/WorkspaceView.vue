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
    </section>

    <TaskHistoryPanel />
  </main>
</template>

<script setup lang="ts">
import BatchJobPanel from "@/components/BatchJobPanel.vue";
import CompliancePanel from "@/components/CompliancePanel.vue";
import GenerationHistoryPanel from "@/components/GenerationHistoryPanel.vue";
import ImageWorkflowPanel from "@/components/ImageWorkflowPanel.vue";
import MaterialInputPanel from "@/components/MaterialInputPanel.vue";
import PlatformResultColumns from "@/components/PlatformResultColumns.vue";
import TaskHistoryPanel from "@/components/TaskHistoryPanel.vue";
</script>
