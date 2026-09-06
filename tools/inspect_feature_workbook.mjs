import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = process.argv[2];
if (!workbookPath) throw new Error("xlsx path is required");

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const overview = await workbook.inspect({
  kind: "workbook,sheet,table,region",
  maxChars: 30000,
  tableMaxRows: 200,
  tableMaxCols: 30,
  tableMaxCellChars: 500,
});
console.log(overview.ndjson);
