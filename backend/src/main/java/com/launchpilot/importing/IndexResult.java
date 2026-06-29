package com.launchpilot.importing;

/** Result summary for bulk indexing operations. */
public record IndexResult(int indexed, int failed) {}
