import type { AxiosProgressEvent } from "axios";
import { defineStore } from "pinia";

class UploadingFile {
  filename: string;
  progress: number;
  total: number;
  loaded: number;
  rate: number;
  finished: boolean;
  failed: boolean;
  failureReason: string;
  phase: "transferring" | "finalizing" | "done" | "failed";

  constructor(filename: string) {
    this.filename = filename;
    this.progress = 0;
    this.total = 0;
    this.loaded = 0;
    this.rate = 0;
    this.finished = false;
    this.failed = false;
    this.failureReason = "";
    this.phase = "transferring";
  }
}

export default defineStore("upload", {
  state: () => ({
    files: [] as UploadingFile[],
  }),
  actions: {
    start(filename: string) {
      this.files = [...this.files, new UploadingFile(filename)];
    },
    update(filename: string, progressEvent: AxiosProgressEvent) {
      const file = this.files.find((f) => f.filename === filename);
      if (!file) return;

      file.progress = progressEvent.progress
        ? progressEvent.progress * 100
        : file.progress;
      file.total = progressEvent.total || file.total;
      file.loaded = progressEvent.loaded;
      file.rate = progressEvent.rate || file.rate;
      file.finished = progressEvent.loaded === progressEvent.total;
    },
    updateChunkProgress(
      filename: string,
      overallPercent: number,
      totalBytes: number,
      rate?: number,
    ) {
      const file = this.files.find((f) => f.filename === filename);
      if (!file) return;

      file.progress = overallPercent;
      file.total = totalBytes;
      file.loaded = (overallPercent / 100) * totalBytes;
      file.rate = rate ?? file.rate;
    },
    finalizing(filename: string) {
      const file = this.files.find((f) => f.filename === filename);
      if (!file) return;
      file.phase = "finalizing";
      file.progress = 100;
      file.loaded = file.total;
      file.finished = false;
    },
    complete(filename: string) {
      const file = this.files.find((f) => f.filename === filename);
      if (file) {
        file.finished = true;
        file.phase = "done";
      }
    },
    fail(filename: string, reason: string) {
      const file = this.files.find((f) => f.filename === filename);
      if (!file) return;

      file.failed = true;
      file.phase = "failed";
      file.failureReason = reason;
    },
    clearFinished() {
      this.files = this.files.filter((f) => !f.finished && !f.failed);
    },
    reset() {
      this.files = [] as UploadingFile[];
    },
  },
});
