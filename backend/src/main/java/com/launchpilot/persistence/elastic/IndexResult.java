package com.launchpilot.persistence.elastic;

/** Result summary for bulk indexing operations. */
public record IndexResult(int indexed, int failed) {}
