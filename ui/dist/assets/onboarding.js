const ui = {
  form: document.getElementById("resumeForm"),
  input: document.getElementById("resumeInput"),
  dropzone: document.getElementById("dropzone"),
  fileName: document.getElementById("fileName"),
  fileMeta: document.getElementById("fileMeta"),
  status: document.getElementById("status"),
  continueBtn: document.getElementById("continueBtn"),
};

let selectedFile = null;

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function setStatus(text, level = "idle") {
  ui.status.textContent = text || "";
  ui.status.dataset.level = level;
}

function selectFile(file) {
  if (!file) return;

  const isPdf =
    file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) {
    setStatus("That is not a PDF. Please choose a .pdf file.", "error");
    return;
  }

  selectedFile = file;
  ui.dropzone.dataset.state = "filled";
  ui.fileName.textContent = file.name;
  ui.fileMeta.textContent = formatSize(file.size);
  ui.continueBtn.disabled = false;
  setStatus("");
}

ui.input.addEventListener("change", (event) => {
  selectFile(event.target.files[0]);
});

// Drag & drop support.
["dragenter", "dragover"].forEach((type) => {
  ui.dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    ui.dropzone.classList.add("is-dragging");
  });
});

["dragleave", "drop"].forEach((type) => {
  ui.dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    ui.dropzone.classList.remove("is-dragging");
  });
});

ui.dropzone.addEventListener("drop", (event) => {
  const file = event.dataTransfer?.files?.[0];
  selectFile(file);
});

ui.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedFile) return;

  ui.continueBtn.disabled = true;
  setStatus("Uploading your resume…", "busy");

  try {
    // Send the raw PDF bytes as the request body (no multipart dependency
    // needed server-side). The filename rides along in a header.
    const response = await fetch("/api/resume", {
      method: "POST",
      headers: {
        "Content-Type": selectedFile.type || "application/pdf",
        "X-Filename": encodeURIComponent(selectedFile.name),
      },
      body: selectedFile,
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.status}`);
    }

    setStatus("Resume saved. Starting your interview…", "ok");
    window.location.href = "./index.html";
  } catch (error) {
    console.error(error);
    setStatus("Could not upload your resume. Please try again.", "error");
    ui.continueBtn.disabled = false;
  }
});
