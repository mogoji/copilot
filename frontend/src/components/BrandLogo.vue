<script setup lang="ts">
withDefaults(
  defineProps<{
    inverse?: boolean
    compact?: boolean
  }>(),
  { inverse: false, compact: false },
)
</script>

<template>
  <div class="flex min-w-0 items-center gap-3">
    <div
      class="grid size-10 shrink-0 grid-cols-2 gap-1 rounded-xl p-2 shadow-sm"
      :class="inverse ? 'bg-white/10 ring-1 ring-white/15' : 'bg-ink-950'"
      aria-hidden="true"
    >
      <span class="rounded-[2px] bg-brand-400"></span>
      <span class="rounded-[2px]" :class="inverse ? 'bg-white' : 'bg-white/90'"></span>
      <span class="rounded-[2px]" :class="inverse ? 'bg-white' : 'bg-white/90'"></span>
      <span class="rounded-[2px] bg-brand-400"></span>
    </div>
    <div v-if="!compact" class="min-w-0 leading-none">
      <p
        class="truncate text-[15px] font-semibold tracking-wide"
        :class="inverse ? 'text-white' : 'text-ink-950'"
      >
        自营后台管理系统
      </p>
      <p
        class="mt-1.5 font-display text-[8px] font-bold tracking-[0.2em]"
        :class="inverse ? 'text-slate-400' : 'text-slate-400'"
      >
        SELF-OPERATED CONSOLE
      </p>
    </div>
  </div>
</template>
