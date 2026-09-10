const statusElement = document.getElementById("fixture-status");

if (statusElement) {
  statusElement.dataset.loadedFrom = "relative-local-script";
  statusElement.textContent = "Loaded from relative local assets.";
}
