package com.launchpilot.importing;

import com.launchpilot.dto.pub.ImportCsvResponse;

/** Handles the frontend CSV import use case. */
public interface ImportUseCase {
    ImportCsvResponse importCsv(CsvImportCommand command);
}
