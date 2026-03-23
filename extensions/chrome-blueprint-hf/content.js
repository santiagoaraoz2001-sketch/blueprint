(() => {
  "use strict";

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  /** Extract the HF dataset id (org/name) from the current URL. */
  function getDatasetId() {
    const match = window.location.pathname.match(/^\/datasets\/([^/]+\/[^/]+)/);
    return match ? match[1] : null;
  }

  /** Show a toast notification overlaying the HF page. */
  function showToast(message, type = "info") {
    let container = document.getElementById("blueprint-toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "blueprint-toast-container";
      document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `blueprint-toast blueprint-toast--${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add("blueprint-toast--fade");
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  /** Send a message to the background service worker and return a promise. */
  function sendMessage(msg) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(msg, (response) => {
        resolve(response || { success: false, error: "No response" });
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Import logic
  // ---------------------------------------------------------------------------

  let importing = false;

  async function handleImportClick() {
    if (importing) return;

    const datasetId = getDatasetId();
    if (!datasetId) {
      showToast("Could not detect dataset ID from this page.", "error");
      return;
    }

    importing = true;
    showToast(`Importing ${datasetId} to Blueprint...`, "info");

    const response = await sendMessage({
      type: "IMPORT_DATASET",
      payload: {
        dataset_id: datasetId,
        split: "train",
        max_samples: 0,
        tags: [],
      },
    });

    importing = false;

    if (response.success) {
      const rows = response.data.row_count;
      showToast(
        `Imported ${datasetId} (${rows != null ? rows + " rows" : "done"}). Open Blueprint to view.`,
        "success"
      );
    } else {
      showToast(`Import failed: ${response.error}`, "error");
    }
  }

  // ---------------------------------------------------------------------------
  // DOM injection — insert "Blueprint" into the "Use this dataset" dropdown
  // ---------------------------------------------------------------------------

  const BLUEPRINT_ITEM_CLASS = "blueprint-hf-menu-item";

  /** Build the Blueprint menu-item element. */
  function createBlueprintItem() {
    const item = document.createElement("button");
    item.className = BLUEPRINT_ITEM_CLASS;
    item.type = "button";

    // Blueprint icon (simple SVG)
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("width", "22");
    icon.setAttribute("height", "22");
    icon.setAttribute("viewBox", "0 0 24 24");
    icon.setAttribute("fill", "none");
    icon.setAttribute("stroke", "currentColor");
    icon.setAttribute("stroke-width", "2");
    icon.setAttribute("stroke-linecap", "round");
    icon.setAttribute("stroke-linejoin", "round");
    // Simple "box-arrow-down" icon representing export/download
    icon.innerHTML =
      '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>' +
      '<polyline points="7 10 12 15 17 10"/>' +
      '<line x1="12" y1="15" x2="12" y2="3"/>';

    const label = document.createElement("span");
    label.textContent = "Blueprint";

    item.appendChild(icon);
    item.appendChild(label);
    item.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      handleImportClick();
    });

    return item;
  }

  /**
   * Try to inject the Blueprint item into an element that looks like the
   * "Use this dataset" dropdown/popover.  HF renders code-snippet panels
   * (Pandas, Datasets, Croissant, etc.) inside a popover/dialog that appears
   * when the user clicks the button.
   *
   * We detect this by looking for elements that:
   *   - Are newly added to the DOM (via MutationObserver)
   *   - Contain text like "datasets", "pandas", "Croissant", or "load_dataset"
   *   - Look like a dropdown/dialog (role=dialog, or a floating panel)
   */
  function tryInject(node) {
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    if (node.querySelector(`.${BLUEPRINT_ITEM_CLASS}`)) return;

    const text = node.textContent || "";
    const lowerText = text.toLowerCase();

    // Match the "Use this dataset" popover content
    const isDatasetPopover =
      (lowerText.includes("load_dataset") || lowerText.includes("pandas") || lowerText.includes("croissant")) &&
      (lowerText.includes("copy") || lowerText.includes("dataset"));

    if (!isDatasetPopover) return;

    // Find a good insertion point — look for the last section/divider or just append
    const item = createBlueprintItem();
    node.appendChild(item);
  }

  // ---------------------------------------------------------------------------
  // MutationObserver — watch for the dropdown to appear
  // ---------------------------------------------------------------------------

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const added of mutation.addedNodes) {
        if (added.nodeType === Node.ELEMENT_NODE) {
          tryInject(added);
          // Also check children (the popover might be nested)
          added.querySelectorAll?.("*").forEach((child) => tryInject(child));
        }
      }
    }
  });

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  async function init() {
    const datasetId = getDatasetId();
    if (!datasetId) return; // Not a valid dataset page

    // Check if Blueprint is running
    const health = await sendMessage({ type: "CHECK_BLUEPRINT" });
    if (!health.running) {
      console.log("[Blueprint Extension] Blueprint is not running on localhost:8000");
    }

    // Start observing for dropdown appearance
    observer.observe(document.body, { childList: true, subtree: true });
  }

  init();
})();
