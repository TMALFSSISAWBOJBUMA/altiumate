procedure run_folder_container(medium_name: string = '');
begin
  ResetParameters;
  AddStringParameter('ObjectKind', 'OutputBatch');
  AddStringParameter('DisableDialog', 'True');
  AddStringParameter('Action', 'Run');
  if (medium_name <> '') then
    AddStringParameter('OutputMedium', medium_name);
  RunProcess('WorkSpaceManager:GenerateReport');
end;

procedure run_pdf_container(medium_name: string = '');
begin
  ResetParameters;
  AddStringParameter('Action', 'PublishToPDF');
  AddStringParameter('ObjectKind', 'OutputBatch');
  AddStringParameter('DisableDialog', 'True');
  if (medium_name <> '') then
    AddStringParameter('OutputMedium', medium_name);
  RunProcess('WorkSpaceManager:Print');
end;

Procedure outjob_run_all(project_path: string, outjob_file_name: string = '');
// Runs all output containers in an output job file.
// project_path: full path to the PrjPcb file.
// outjob_file_name: determines the outjob file name to be executed, if not provided, first file found in the project will be used.
Var
  n: cardinal;
  containers: TStrings;
  line, name, job_path: string;
  job_file: TextFile;
  opened: boolean;
  doc: IServerDocument;
  project: IProject;
Begin

  // open project from path
  ResetParameters;
  AddStringParameter('ObjectKind', 'Project');
  AddStringParameter('FileName', project_path);
  RunProcess('WorkspaceManager:OpenObject');

  // workspace methods that don't work:
  // project := GetWorkspace.DM_GetProjectFromDocumentPath(project_path);
  // project := GetProjectByDocumentPath(project_path);

  // try matching project from the ones opened in the workspace
  for n := 0 to GetWorkspace.DM_ProjectCount - 1 do
  begin
    project := GetWorkspace.DM_Projects(n);
    if project = nil then
      Break;

    if AnsiCompareFileName(project_path, project.DM_ProjectFullPath, false) = 0
    then
      Break;
  end;

  if check_val(project, nil, 'Failed to open the project') then
    exit;

  job_path := '';
  for n := 0 to project.DM_LogicalDocumentCount - 1 do
  begin
    doc := project.DM_LogicalDocuments(n);
    if doc = nil then
      Break;

    if doc.DM_DocumentKind = 'OUTPUTJOB' then
    Begin
      if (outjob_file_name = '') or
        ((outjob_file_name <> '') and
        AnsiCompareText(ExtractFileNameFromPath(doc.DM_FullPath),
        ExtractFileNameFromPath(outjob_file_name)) = 0) then
        job_path := doc.DM_FullPath;
    end;
  end;

  if check_val(job_path, '', 'OutJob file not found!') then
    exit;

  // parse output containers names from the file
  AssignFile(job_file, job_path);
  containers := TStringList.Create;
  try
    Reset(job_file);
    while not Eof(job_file) do
    begin
      ReadLn(job_file, line);
      if (line <> Null) then
      begin
        if LeftStr(line, 12) = 'OutputMedium' then
        begin
          name := string_after_char(line, '=');
          ReadLn(job_file, line);
          containers.Values[name] := string_after_char(line, '=');
        end;
      end;
    end;
  finally
    CloseFile(job_file);
  end;

  if Client.IsDocumentOpen(job_path) then
    opened := true
  else
    opened := false;

  doc := Client.OpenDocument('OUTPUTJOB', job_path);
  if check_val(doc, nil, 'Opening the OutJob file failed') then
    exit;
  Client.ShowDocument(doc);

  for n := 0 to containers.Count - 1 do
  begin
    name := containers.Names[n];
    case containers.Values[name] of
      'GeneratedFiles':
        run_folder_container(name);
      'Publish':
        run_pdf_container(name);
    end;
  end;
  containers.Free;

  if opened <> true then
    Client.CloseDocument(doc);

End;
