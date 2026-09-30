# Create the official OMOP CDM v5.4 indices (CommonDataModel v5.4.3) after the data is loaded.
#
# ETL-Synthea's CreateCDMTables() can create them (createIndices = TRUE), but it does so before the
# load, which slows the bulk inserts and CLUSTERs empty tables. Without them the vocabulary tables
# only have concept's primary key, so any lookup on concept_relationship (~34M rows) or
# concept_ancestor (~29M rows) is a full scan.
#
# Idempotent: CREATE INDEX becomes CREATE INDEX IF NOT EXISTS, so it can be re-run on an existing
# database. Sourced at the end of run_etl_synthea.R, or run alone:
#   docker compose --profile etl run --rm etl Rscript /etl/create_indices.R

if (!exists("cd")) {
  cd <- DatabaseConnector::createConnectionDetails(
    dbms         = "postgresql",
    server       = paste0(Sys.getenv("DB_HOST"), "/", Sys.getenv("POSTGRES_DB")),
    user         = Sys.getenv("POSTGRES_USER"),
    password     = Sys.getenv("POSTGRES_PASSWORD"),
    port         = 5432,
    pathToDriver = Sys.getenv("DATABASECONNECTOR_JAR_FOLDER")
  )
}
cdmSchema <- if (exists("cdmSchema")) cdmSchema else "cdm"

message(format(Sys.time(), "%H:%M:%S"), " START create CDM indices")
t0 <- Sys.time()

indexFile <- CommonDataModel::writeIndex(
  targetDialect = "postgresql", cdmVersion = "5.4", cdmDatabaseSchema = cdmSchema,
  outputfolder = tempdir()
)
indexSql <- SqlRender::readSql(file.path(tempdir(), indexFile))
indexSql <- gsub("CREATE INDEX (?!IF NOT EXISTS)", "CREATE INDEX IF NOT EXISTS ", indexSql,
                 perl = TRUE)

conn <- DatabaseConnector::connect(cd)
DatabaseConnector::executeSql(conn, indexSql)
DatabaseConnector::executeSql(conn, "ANALYZE;")
DatabaseConnector::disconnect(conn)

message(format(Sys.time(), "%H:%M:%S"), " DONE  create CDM indices (",
        round(as.numeric(difftime(Sys.time(), t0, units = "mins")), 1), " min)")
