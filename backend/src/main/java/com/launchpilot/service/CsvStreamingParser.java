package com.launchpilot.service;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BiConsumer;
import org.springframework.stereotype.Component;

/**
 * OOM 방지용 줄 단위 스트리밍 파서 (C4 CsvStreamingParser).
 * 해커톤 CSV 가정: 단순 콤마 구분, 따옴표 필드 최소 지원.
 */
@Component
public class CsvStreamingParser {

    public record Header(List<String> columns) {}

    /**
     * 헤더를 반환하고, 데이터 행마다 (rowNumber, columnValueMap)을 콜백으로 전달한다.
     * rowNumber는 1부터 (데이터 행 기준).
     */
    public Header parse(InputStream in, BiConsumer<Integer, Map<String, String>> rowConsumer)
            throws IOException {
        try (BufferedReader reader =
                new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            String headerLine = reader.readLine();
            if (headerLine == null) {
                throw ApiException.badRequest("empty CSV");
            }
            List<String> columns = splitCsv(headerLine);
            if (columns.isEmpty()) {
                throw ApiException.badRequest("CSV header has no columns");
            }

            String line;
            int rowNumber = 0;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }
                rowNumber++;
                List<String> values = splitCsv(line);
                Map<String, String> row = new LinkedHashMap<>();
                for (int i = 0; i < columns.size(); i++) {
                    row.put(columns.get(i), i < values.size() ? values.get(i) : "");
                }
                rowConsumer.accept(rowNumber, row);
            }
            return new Header(columns);
        }
    }

    private List<String> splitCsv(String line) {
        List<String> out = new ArrayList<>();
        StringBuilder cur = new StringBuilder();
        boolean inQuotes = false;
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (c == '"') {
                inQuotes = !inQuotes;
            } else if (c == ',' && !inQuotes) {
                out.add(cur.toString().trim());
                cur.setLength(0);
            } else {
                cur.append(c);
            }
        }
        out.add(cur.toString().trim());
        return out;
    }
}
