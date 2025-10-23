function doc_modified(path: string): bool;
var
  doc: IServerDocument;

begin
  doc := Client.GetDocumentByPath(path);
  if doc <> nil then
    result := doc.Modified;
end;

function modified_docs_in_project(project_path: string): bool;
// Checks if there are any modified files in the project.
// project_path: full path to the PrjPcb file.
Var
  n: cardinal;
  doc: IDocument;
  project: IProject;
Begin
  result := false;
  project := get_project(project_path);
  if check_val(project, nil, 'Failed to open the project') then
    exit;

  if doc_modified(project_path) then
  begin
    result := true;
    exit;
  end;

  for n := 0 to project.DM_LogicalDocumentCount - 1 do
  begin
    doc := project.DM_LogicalDocuments(n);
    if (doc = nil) or (doc.DM_DocumentIsLoaded <> true) then
      Continue;

    if doc_modified(doc.DM_FullPath) then
    begin
      result := true;
      break;
    end;
  end;
End;
