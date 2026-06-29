package com.launchpilot.importing;

import com.launchpilot.contracts.frontend.ImportCsvResponse;

/** Handles the frontend CSV import use case. */
public interface ImportUseCase {
    ImportCsvResponse importCsv(CsvImportCommand command);
}
