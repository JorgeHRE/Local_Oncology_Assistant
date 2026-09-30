# Build an OMOP CDM v5.4 database from Synthea CSVs using the official ETL-Synthea package.
# Configuration comes from environment variables (set in compose.yml / .env).
# Steps follow the ETL-Synthea README order; see docs/adr/0001-datos-sinteticos-cancer-gastrico.md.

cdmSchema      <- "cdm"
syntheaSchema  <- "native"
cdmVersion     <- "5.4"
syntheaVersion <- "3.3.0"  # highest version ETL-Synthea v2.1.1 supports; must match the generator

cd <- DatabaseConnector::createConnectionDetails(
  dbms         = "postgresql",
  server       = paste0(Sys.getenv("DB_HOST"), "/", Sys.getenv("POSTGRES_DB")),
  user         = Sys.getenv("POSTGRES_USER"),
  password     = Sys.getenv("POSTGRES_PASSWORD"),
  port         = 5432,
  pathToDriver = Sys.getenv("DATABASECONNECTOR_JAR_FOLDER")
)

step <- function(label, expr) {
  message(format(Sys.time(), "%H:%M:%S"), " START ", label)
  t0 <- Sys.time()
  force(expr)
  message(format(Sys.time(), "%H:%M:%S"), " DONE  ", label, " (",
          round(as.numeric(difftime(Sys.time(), t0, units = "mins")), 1), " min)")
}

step("create CDM tables", ETLSyntheaBuilder::CreateCDMTables(cd, cdmSchema, cdmVersion))
step("create Synthea tables", ETLSyntheaBuilder::CreateSyntheaTables(cd, syntheaSchema, syntheaVersion))
step("load Synthea CSVs", ETLSyntheaBuilder::LoadSyntheaTables(
  cd, syntheaSchema, Sys.getenv("SYNTHEA_CSV_DIR"), bulkLoad = TRUE))
step("load vocabulary", ETLSyntheaBuilder::LoadVocabFromCsv(
  cd, cdmSchema, Sys.getenv("VOCAB_DIR"), bulkLoad = TRUE))
step("create map and rollup tables", ETLSyntheaBuilder::CreateMapAndRollupTables(
  cd, cdmSchema, syntheaSchema, cdmVersion, syntheaVersion))
step("create extra indices", ETLSyntheaBuilder::CreateExtraIndices(
  cd, cdmSchema, syntheaSchema, syntheaVersion))
step("load event tables", ETLSyntheaBuilder::LoadEventTables(
  cd, cdmSchema, syntheaSchema, cdmVersion, syntheaVersion))
# Official CDM indices, after the load (see the header of create_indices.R).
source("/etl/create_indices.R")
