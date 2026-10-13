<script lang="ts">
  interface Props {
    title?: string;
  }

  let { title = "Eternity Studio 🎬" }: Props = $props();
  let activeTab = $state<"timeline" | "concepts" | "preview">("timeline");
</script>

<div class="eternity-studio-root">
  <div class="studio-header">
    <span class="studio-badge">ALPHA</span>
    <span class="studio-title">{title}</span>
    <div class="studio-nav">
      <button class:active={activeTab === 'timeline'} onclick={() => activeTab = 'timeline'}>Timeline</button>
      <button class:active={activeTab === 'concepts'} onclick={() => activeTab = 'concepts'}>Concepts</button>
      <button class:active={activeTab === 'preview'} onclick={() => activeTab = 'preview'}>Preview</button>
    </div>
  </div>
  <div class="studio-body">
    {#if activeTab === 'timeline'}
      <div class="panel">Timeline Workspace Initialized</div>
    {:else if activeTab === 'concepts'}
      <div class="panel">Global References & Concepts Pool</div>
    {:else}
      <div class="panel">Live Canvas Playback Monitor</div>
    {/if}
  </div>
</div>

<style>
  .eternity-studio-root {
    display: flex;
    flex-direction: column;
    background: #18181b;
    color: #f4f4f5;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    border-radius: 8px;
    border: 1px solid #27272a;
    overflow: hidden;
  }
  .studio-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: #09090b;
    border-bottom: 1px solid #27272a;
  }
  .studio-badge {
    background: #6366f1;
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    letter-spacing: 0.5px;
  }
  .studio-title {
    font-weight: 600;
    font-size: 13px;
  }
  .studio-nav {
    margin-left: auto;
    display: flex;
    gap: 4px;
  }
  .studio-nav button {
    background: transparent;
    border: none;
    color: #a1a1aa;
    padding: 4px 8px;
    font-size: 11px;
    cursor: pointer;
    border-radius: 4px;
    transition: all 0.15s ease;
  }
  .studio-nav button:hover {
    background: #27272a;
    color: #fff;
  }
  .studio-nav button.active {
    background: #312e81;
    color: #c7d2fe;
    font-weight: 600;
  }
  .studio-body {
    padding: 12px;
  }
  .panel {
    font-size: 12px;
    color: #a1a1aa;
  }
</style>
