# R environment for ETL-Synthea. rocker/r-ver pins CRAN to a dated snapshot for its R version,
# so package versions are reproducible; OHDSI packages are pinned to release tags below.
FROM rocker/r-ver:4.5.3

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openjdk-17-jdk-headless \
        postgresql-client \
        libxml2-dev libssl-dev libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && R CMD javareconf

RUN install2.r --error --skipinstalled remotes rJava \
    && Rscript -e 'remotes::install_github("OHDSI/CommonDataModel@v5.4.3", upgrade = "never")' \
    && Rscript -e 'remotes::install_github("OHDSI/ETL-Synthea@v2.1.1", upgrade = "never")' \
    && Rscript -e 'DatabaseConnector::downloadJdbcDrivers("postgresql", pathToDriver = "/opt/jdbc")'

# DatabaseConnector's bulk load for PostgreSQL shells out to psql from this directory.
ENV DATABASECONNECTOR_JAR_FOLDER=/opt/jdbc \
    POSTGRES_PATH=/usr/bin

WORKDIR /etl
CMD ["Rscript", "/etl/run_etl_synthea.R"]
