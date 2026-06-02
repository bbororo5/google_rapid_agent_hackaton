package com.launchpilot.dto.common;

/** 계약: { start: date, end: date }. 형식 드리프트 방지를 위해 String 보존. */
public record DateRange(String start, String end) {}
