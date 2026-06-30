import { describe, expect, it } from "vitest";

import { taskJobEventsUrl } from "./client";

describe("task progress client", () => {
  it("builds encoded event stream URLs", () => {
    expect(taskJobEventsUrl("task id/1")).toBe("/api/task_jobs/task%20id%2F1/events");
  });
});
