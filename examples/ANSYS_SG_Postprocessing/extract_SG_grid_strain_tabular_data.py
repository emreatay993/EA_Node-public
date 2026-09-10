# region Import necessary libraries
import csv
import time
import os
import re
from System.Windows.Forms import MessageBox,MessageBoxButtons, MessageBoxIcon
# endregion

# ----------------------------------------------------------------------------------------------------------------

PREF_LEVEL_OF_DETAIL = "PID_Level_Of_Detail"
# Ansys maps this enum as 0=No Graphics, 1=Low Graphics, 2=Medium, 3=Full.
PREF_LEVEL_OF_DETAIL_LOW_GRAPHICS = "1"

# region Define the required functions
# Function to extract reference and channel numbers from a strain name
def extract_numbers(name):
    pattern = r"StrainX_SG(\d+)_(\d+)"
    match = re.search(pattern, name)
    if match:
        return tuple(map(int, match.groups()))
    else:
        return (0, 0)  # Default to (0, 0) if the pattern does not match

# Function to sort the strain names using the extract_numbers function
def sort_strain_names(names):
    sorted_names = sorted(names, key=extract_numbers)
    return sorted_names


def log_message(message):
    print(message)
    try:
        ExtAPI.Log.WriteMessage(str(message))
    except Exception:
        pass


def get_app_preference(pref_id, default_value=None):
    try:
        pref_val = ExtAPI.Application.GetPreference(pref_id)
        if pref_val is None:
            return default_value
        pref_str = str(pref_val)
        if pref_str == "":
            return default_value
        return pref_str
    except Exception:
        pass

    try:
        cmd = "returnFromScript(DS.Script.wb.PreferenceMgr.Preference('{0}'));".format(pref_id)
        pref_val = ExtAPI.Application.ScriptByName("jscript").ExecuteCommand(cmd)
        if pref_val is None:
            return default_value
        pref_str = str(pref_val)
        if pref_str == "":
            return default_value
        return pref_str
    except Exception:
        return default_value


def set_app_preference(pref_id, pref_value):
    value_str = str(pref_value)
    try:
        ExtAPI.Application.SetPreference(pref_id, value_str)
        return True
    except Exception:
        pass

    try:
        cmd = (
            "DS.Script.wb.PreferenceMgr.Preference('{0}') = '{1}';"
            "DS.Script.wb.PreferenceMgr.Save();"
            "returnFromScript(DS.Script.wb.PreferenceMgr.Preference('{0}'));"
        ).format(pref_id, value_str)
        new_val = ExtAPI.Application.ScriptByName("jscript").ExecuteCommand(cmd)
        if new_val is None:
            return True
        return str(new_val) == value_str
    except Exception:
        return False


def enter_low_graphics_preference_mode():
    original_val = get_app_preference(PREF_LEVEL_OF_DETAIL, None)
    changed_ok = set_app_preference(PREF_LEVEL_OF_DETAIL, PREF_LEVEL_OF_DETAIL_LOW_GRAPHICS)
    if changed_ok:
        log_message("Set preference {0}=1 for low graphics during SG strain extraction.".format(PREF_LEVEL_OF_DETAIL))
    else:
        log_message("Warning: could not set {0}=1 for low graphics in this Mechanical session.".format(PREF_LEVEL_OF_DETAIL))
    return {
        "pref_id": PREF_LEVEL_OF_DETAIL,
        "original_value": original_val,
        "restore_needed": original_val is not None and str(original_val) != PREF_LEVEL_OF_DETAIL_LOW_GRAPHICS,
    }


def restore_low_graphics_preference_mode(pref_state):
    if pref_state is None or not pref_state.get("restore_needed", False):
        return

    pref_id = pref_state.get("pref_id", PREF_LEVEL_OF_DETAIL)
    original_val = pref_state.get("original_value", None)
    if original_val is None:
        return

    restored_ok = set_app_preference(pref_id, str(original_val))
    if restored_ok:
        log_message("Restored preference {0} back to {1}.".format(pref_id, str(original_val)))
    else:
        log_message("Warning: could not restore {0} to {1}. Please check Mechanical Options > Graphics.".format(pref_id, str(original_val)))


def restore_ui_interaction_state():
    try:
        ExtAPI.DataModel.Tree.Refresh()
    except Exception:
        pass
    try:
        ExtAPI.Graphics.Redraw()
    except Exception:
        pass


def expected_result_row_count(solution):
    try:
        solution_id = solution.ObjectId
        for analysis in Model.Analyses:
            if analysis.Solution.ObjectId == solution_id:
                result_data = analysis.GetResultsData()
                return len(result_data.ListTimeFreq)
    except Exception:
        pass

    try:
        result_data = solution.Parent.GetResultsData()
        return len(result_data.ListTimeFreq)
    except Exception:
        return None
# endregion

# ----------------------------------------------------------------------------------------------------------------

# region Get the solution directory and the path
solution_directory_path = sol_selected_environment.WorkingDir
solution_directory_path = solution_directory_path.Replace("\\", "\\\\")
# endregion

# region Get the the names of active StrainX_SG objects in the selected analysis environment
list_of_names_of_SG_grid_strains = [] # Initialize the list

list_of_obj_of_all_elastic_strains = sol_selected_environment.GetChildren(DataModelObjectCategory.NormalElasticStrain,True)
list_of_names_of_SG_grid_strains = [
    obj.Name for obj in list_of_obj_of_all_elastic_strains
    if obj.Name.Contains("StrainX_SG")
    and obj.ObjectState != ObjectState.Suppressed]

list_of_IDs_of_SG_grid_strains = [
    obj.ObjectId for obj in list_of_obj_of_all_elastic_strains
    if obj.Name.Contains("StrainX_SG")
    and obj.ObjectState != ObjectState.Suppressed]

# Throw an error if no active StrainX_SG objects are found in the selected analysis environment.
if len(list_of_names_of_SG_grid_strains) == 0:
    MessageBox.Show("There are no active SG strain contours to be extracted within the selected analysis environment.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
# endregion

# ----------------------------------------------------------------------------------------------------------------

# region Make sure that all StrainX_SG objects are and will be evaluated in the ascending order.
# Pair each ID with its corresponding name
paired_list = list(zip(list_of_IDs_of_SG_grid_strains, list_of_names_of_SG_grid_strains))

# Use your existing sort function on the paired list, sorting by the second element of each pair (the name)
sorted_pairs = sorted(paired_list, key=lambda x: extract_numbers(x[1]))

# Unzip the pairs back into two lists
sorted_IDs, sorted_names = zip(*sorted_pairs)

# Convert tuples back to lists, if necessary
list_of_IDs_of_SG_grid_strains = list(sorted_IDs)
list_of_names_of_SG_grid_strains = list(sorted_names)
# endregion

# ----------------------------------------------------------------------------------------------------------------

# region Convert the tabular data contained in each StrainX_SG result into numerical data
# Helper function to check if a string can be converted to float
def is_float(element):
    try:
        float(element)
        return True
    except ValueError:
        return False


def read_tabular_columns(object_id):
    DataModel.GetObjectById(object_id).Activate()
    Pane = ExtAPI.UserInterface.GetPane(MechanicalPanelEnum.TabularData)
    Con = Pane.ControlUnknown

    flat_list = []
    for C in range(1, Con.ColumnsCount + 1):
        for R in range(1, Con.RowsCount + 1):
            Text = Con.cell(R, C).Text
            if Text is not None:
                flat_list.append(Text)

    numeric_list = [float(item) for item in flat_list if is_float(item)]
    num_elements_per_column = len(numeric_list) // 5
    columns = [numeric_list[i * num_elements_per_column: (i + 1) * num_elements_per_column] for i in range(5)]
    return columns, num_elements_per_column

time_data = []
list_of_strain_data = []
headers_strain = []
headers_microstrain = []
graphics_pref_state = None
expected_row_count = expected_result_row_count(sol_selected_environment)
low_graphics_table_read_enabled = True

try:
    graphics_pref_state = enter_low_graphics_preference_mode()

    for m in range(len(list_of_names_of_SG_grid_strains)):
        columns, num_elements_per_column = read_tabular_columns(
            list_of_IDs_of_SG_grid_strains[m]
        )

        if (
            low_graphics_table_read_enabled
            and expected_row_count is not None
            and num_elements_per_column != expected_row_count
        ):
            log_message(
                "Low graphics table read returned {0} rows; expected {1}. Restoring graphics and rereading tabular data.".format(
                    num_elements_per_column, expected_row_count
                )
            )
            restore_low_graphics_preference_mode(graphics_pref_state)
            restore_ui_interaction_state()
            graphics_pref_state = None
            low_graphics_table_read_enabled = False

            columns, num_elements_per_column = read_tabular_columns(
                list_of_IDs_of_SG_grid_strains[m]
            )

        if expected_row_count is not None and num_elements_per_column != expected_row_count:
            raise Exception(
                "Tabular data row count mismatch for {0}: read {1}, expected {2}.".format(
                    list_of_names_of_SG_grid_strains[m],
                    num_elements_per_column,
                    expected_row_count,
                )
            )

        # Use regular expressions to extract the "SG_x_y" part
        match = re.search(r"(SG\d+_\d+)", list_of_names_of_SG_grid_strains[m])
        if match:
            sg_name = match.group(1)  # Extract the "SG_x_y" part
        else:
            sg_name = "Unknown"  # Default value if the pattern doesn't match

        # Extract and modify the names of each column data
        headers_strain.append(sg_name)
        headers_microstrain.append(sg_name)

        # Assuming each inner list of columns is a separate column of data
        list_of_strain_data.append(columns[4])

    time_data.append(columns[1])
    time_data = time_data[0]

    # Add Time as the first header in both headers lists
    headers_strain.insert(0, "Time")
    headers_microstrain.insert(0, "Time")

    # Transpose the list of lists so each inner list becomes a column
    transposed_data = list(map(list, zip(*list_of_strain_data)))

    # Define the path where you want to save the CSV file for strain data
    csv_file_name = "SG_FEA_strain_data.csv"
    file_path = os.path.join(solution_directory_path, csv_file_name)

    # Write the original strain data to a CSV file
    with open(file_path, 'wb') as file:
        writer = csv.writer(file)
        writer.writerow(headers_strain)  # Write the header row first
        for index, row in enumerate(transposed_data):
            writer.writerow([time_data[index]] + row)  # Prepend time data to each row

    print("CSV file for each SG channel (strain in mm/mm) created at: " + file_path)

    # Create a new list of lists with the values multiplied by 1e6 for microstrain
    SG_FEA_microstrain_data = [[value * 1e6 for value in row] for row in transposed_data]

    # Define the path for the microstrain CSV file
    SG_FEA_microstrain_csv_file_name = "SG_FEA_microstrain_data.csv"
    SG_FEA_microstrain_file_path = os.path.join(solution_directory_path, SG_FEA_microstrain_csv_file_name)

    # Write the microstrain data to a CSV file
    with open(SG_FEA_microstrain_file_path, 'wb') as file:
        writer = csv.writer(file)
        writer.writerow(headers_microstrain)  # Write the header row first
        for index, row in enumerate(SG_FEA_microstrain_data):
            writer.writerow([time_data[index]] + row)  # Prepend time data to each row

    print("CSV file for each SG channel (microstrain) created at: " + SG_FEA_microstrain_file_path)
finally:
    restore_low_graphics_preference_mode(graphics_pref_state)
    restore_ui_interaction_state()
# endregion
