"use strict";

(() => {
  const FILES = [
    ["manifest.json", "/local-events/feedback-extension/manifest.json"],
    ["service_worker.js", "/local-events/feedback-extension/service_worker.js"],
    ["content.js", "/local-events/feedback-extension/content.js"],
  ];

  const encoder = new TextEncoder();

  function u16(value) {
    return new Uint8Array([value & 255, (value >>> 8) & 255]);
  }

  function u32(value) {
    return new Uint8Array([
      value & 255,
      (value >>> 8) & 255,
      (value >>> 16) & 255,
      (value >>> 24) & 255,
    ]);
  }

  function concat(parts) {
    const length = parts.reduce((total, part) => total + part.length, 0);
    const output = new Uint8Array(length);
    let offset = 0;
    for (const part of parts) {
      output.set(part, offset);
      offset += part.length;
    }
    return output;
  }

  function crc32(bytes) {
    let crc = 0xffffffff;
    for (const byte of bytes) {
      crc ^= byte;
      for (let bit = 0; bit < 8; bit += 1) {
        crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
      }
    }
    return (crc ^ 0xffffffff) >>> 0;
  }

  function dosTime(date) {
    return ((date.getHours() & 31) << 11)
      | ((date.getMinutes() & 63) << 5)
      | ((Math.floor(date.getSeconds() / 2)) & 31);
  }

  function dosDate(date) {
    return (((Math.max(1980, date.getFullYear()) - 1980) & 127) << 9)
      | (((date.getMonth() + 1) & 15) << 5)
      | (date.getDate() & 31);
  }

  async function fetchFile(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`Unable to read ${path}: HTTP ${response.status}`);
    return encoder.encode(await response.text());
  }

  async function buildZip() {
    const now = new Date();
    const localParts = [];
    const centralParts = [];
    let offset = 0;

    for (const [name, path] of FILES) {
      const nameBytes = encoder.encode(name);
      const data = await fetchFile(path);
      const crc = crc32(data);
      const local = concat([
        u32(0x04034b50),
        u16(20),
        u16(0),
        u16(0),
        u16(dosTime(now)),
        u16(dosDate(now)),
        u32(crc),
        u32(data.length),
        u32(data.length),
        u16(nameBytes.length),
        u16(0),
        nameBytes,
        data,
      ]);
      const central = concat([
        u32(0x02014b50),
        u16(20),
        u16(20),
        u16(0),
        u16(0),
        u16(dosTime(now)),
        u16(dosDate(now)),
        u32(crc),
        u32(data.length),
        u32(data.length),
        u16(nameBytes.length),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(0),
        u32(offset),
        nameBytes,
      ]);
      localParts.push(local);
      centralParts.push(central);
      offset += local.length;
    }

    const localData = concat(localParts);
    const centralData = concat(centralParts);
    const end = concat([
      u32(0x06054b50),
      u16(0),
      u16(0),
      u16(FILES.length),
      u16(FILES.length),
      u32(centralData.length),
      u32(localData.length),
      u16(0),
    ]);
    return new Blob([localData, centralData, end], { type: "application/zip" });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const button = document.getElementById("download-feedback-helper");
    if (!button) return;

    button.addEventListener("click", async (event) => {
      event.preventDefault();
      const original = button.textContent;
      button.setAttribute("aria-disabled", "true");
      button.textContent = "BUILDING ZIP...";
      try {
        const blob = await buildZip();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "infoscreen-local-event-feedback-extension.zip";
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (error) {
        const message = document.getElementById("feedback-message");
        if (message) message.textContent = String(error?.message || error);
      } finally {
        button.removeAttribute("aria-disabled");
        button.textContent = original;
      }
    });
  });
})();
