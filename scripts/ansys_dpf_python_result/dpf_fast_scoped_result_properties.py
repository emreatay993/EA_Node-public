def reload_props():
    this.PropertyProvider = None

    provider = Provider()
    group = provider.AddGroup('DPF Extraction')

    result_prop = group.AddProperty('Result', Control.Options)
    result_prop.Options = {1: 'Total Deformation', 2: 'Equivalent Stress', 3: 'Equivalent Elastic Strain'}
    result_prop.Value = 1

    ns_prop = group.AddProperty('Named Selection', Control.Expression)
    ns_prop.Value = 'NS_BODY_MIDDLE'

    sets_prop = group.AddProperty('Time Set IDs', Control.Expression)
    sets_prop.Value = 'last'

    location_prop = group.AddProperty('Requested Location', Control.Options)
    location_prop.Options = {1: 'Nodal', 2: 'Elemental', 3: 'ElementalNodal'}
    location_prop.Value = 1

    this.PropertyProvider = provider

# region Property Provider Template
from Ansys.ACT.Mechanical.AdditionalProperties import PropertyProviderAdapter
from Ansys.ACT.Mechanical.AdditionalProperties import *

"""
The property_templates module is located in %awp_root212%\aisol\DesignSpace\DSPages\IronPython\mech_templates
"""
from mech_templates import property_templates

property_templates.set_ext_api(ExtAPI)

class Provider(Ansys.ACT.Interfaces.Mechanical.IPropertyProvider):
    """
    Provider template that implements IPropertyProvider to demonstrate the usage of IPropertyProvider.
    It provides helper methods and classes that manage properties that can be dynamically added to an object.
    """

    __namespace__ = "Python.Ansys.ACT.Interfaces.Mechanical.IPropertyProvider"
    
    # region These are callbacks that as a user you may want to modify to get specific behavior
    def IsValid(self, prop):
        """
        Called when checking the validity of a property, with the property instance.
        """

        # for double property use the ValidRange property to check validity
        if(isinstance(prop, DoubleProperty)):
            return prop.ValidRange[0] <= prop.Value and prop.ValidRange[1] >= prop.Value
        
        return True
    
    def IsReadOnly(self, prop):
        """
        Called when checking if a property should be readonly, with the property instance.
        """

        return False
    
    def IsVisible(self, prop):
        """
        Called when checking if a property should be visible, with the property instance.
        """

        return True
    
    def SetValue(self, prop, val):
        """
        Allows you to override the setter of the Value property on the property instance. 
        Keyword Arguments:
            prop -- property of which the value is being set
            val -- the value that was set
        Returns:
            The value that the Value property should be set to
        """
        return val

    def GetValue(self, prop, val):
        """
        Allows you to override the getter of the Value property on the property instance. 
        Keyword Arguments:
            prop -- property of which the value is being set
            val -- current value of the Value property
        Returns:
            The value that the getter on the internal value should return
        """
        return val
    # endregion   
    
    # structures that hold property instances
    prop_list = []
    prop_map = {}
    prop_groups = set()

    class __AnsGroup():
        """
        Helper group class to group properties, and provides methods to add properties to groups.
        """
        provider = None
        def __init__(self,name=None, provider=None):
            self.name = name
            self.provider = provider
        
        def __AddScopingProperty(self, name):
            """
            Adds a scoping property with a given name to this group.
            
            Keyword Arguments : 
                name -- unique name for the scoping property
            """
            scoping_prop = property_templates.ScopingProperty(name, self.name)
            
            for prop in scoping_prop.GetGroupedProps():
                self.provider.AddProperty(prop)
            return scoping_prop.GetGroupedProps()
        
        def AddProperty(self, name=None, prop_control=None, module_name=None):
            """
            Creates an instance of the property and connects delgates in 
            the associated Property Propvider.

            Keyword Arguments : 
                name -- unique name for the scoping property
                prop_control -- one of the built in controls, or extended controls
                module_name -- module where the control is defined
            """

            #special case for scoping property
            if(prop_control == "Scoping" and module_name == "property_templates"):
                return self.__AddScopingProperty(name)
            
            #if no module_name is passed, use the globals in current module
            #that has the built in controls imported
            prop_mod_globals = None
            if(module_name != None):
                if(module_name not in globals()):
                    raise Exception("Unknown module : " + module_name)
                
                prop_mod_globals = globals()[module_name].get_globals()
            else:
                prop_mod_globals = globals()
            
            #class name is built based on control + "Property"
            #    Double - > DoubleProperty
            prop_class_name = str(prop_control) + "Property"
            
            if(prop_class_name not in prop_mod_globals):
                raise Exception("Unknown property class : " + prop_class_name)
            
            #instantiate the property based on module and class name
            prop = prop_mod_globals[prop_class_name](self.name + "/" + name, self.name)
            
            if(prop == None):
                raise Exception("Issue while creating the property instance.")
            
            #set the delegates to property provider functions
            prop.IsValidCallback = self.provider.IsValid
            prop.IsReadOnlyCallback = self.provider.IsReadOnly
            prop.IsVisibleCallback = self.provider.IsVisible
            prop.GetValueCallback = self.provider.GetValue
            prop.SetValueCallback = self.provider.SetValue

            #as a default make the property name the property display name
            prop.DisplayName = name
            
            #add property to the provider
            self.provider.AddProperty(prop)
            
            return prop
        
    def __init__(self):
        pass

    def GetProperties(self):
        """
        Returns a list of properties in the order that they were added to the property provider. 
        """
        return [self.prop_map[propName] for propName in self.prop_list]
    
    def AddGroup(self, name=None):
        """
        Creates an instance of helper group class and returns it.
        """
        if name in self.prop_groups:
            raise Exception("Group with name " + name + " already exists, please use a unique group name.")
        
        #keep groups names so we can make sure no duplicate groups are added
        self.prop_groups.add(name)
        
        return self.__AnsGroup(name, self)
    
    def AddProperty(self, prop):
        """
        Method used by the helper group class to add the property to the data-structure holding
        the property instances.
        """
        if(prop.Name in self.prop_map):
            raise Exception("Property name must be unique, property with name '" + prop.Name + "' already exisits.")
        
        self.prop_list.append(prop.Name)
        self.prop_map[prop.Name] = prop
#end region



"""
Reload the properties at the end to make sure the class definition is executed before instantiation
"""
reload_props()

