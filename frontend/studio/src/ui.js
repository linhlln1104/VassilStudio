export const $ = (selector) => document.querySelector(selector);

export function formatBytes(value) {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDuration(value) {
  return `${Number(value || 0).toFixed(2)}s`;
}

export async function withBusy(targets, work) {
  const buttons = (Array.isArray(targets) ? targets : [targets]).filter(Boolean);
  const previousDisabled = new Map(buttons.map((button) => [button, button.disabled]));
  for (const button of buttons) {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  }
  try {
    await work();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    for (const button of buttons) {
      button.disabled = previousDisabled.get(button) || false;
      button.removeAttribute("aria-busy");
    }
  }
}

export function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.style.borderColor = isError ? "var(--danger)" : "var(--line)";
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 2600);
}
