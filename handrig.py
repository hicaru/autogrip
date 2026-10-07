"""INSTRUCTIONS
Run "autogrip.py" in Blender's text editor or install it as an add-on through the preferences menu. 
Once that's done, check object mode, and all the buttons you need are in a tab in the N-panel called 
"AutoGrip."

With the armature you want to use selected, you can pick which type of rig it is from the drop-down.
Formats supported so far are MakeHuman Exchange, Rigify, and Auto-Rig Pro. 

If it's not a model you made and you're not 100% sure, you can use "Guess Rig Type" to quickly
 compare its hand setup to the ones this program can handle.

Click "setup" to assemble both hands, or just "Setup Right" or "Setup Left" if you don't need both
(or your model doesn't have both).

It'll take about 20-30 seconds, during which a lot of my debug notes will print in the system 
console. Let that finish, and you'll have a tangle of small needley bones sticking off the hands, 
but the pose won't change yet. (If you don't seem to have the small needley bones, check the 
tooltip for the rig type you chose and make sure you can actually see the layer where it left them.)

The influence of the contraints depends on the rotation of the control bones - those are the longer
ones that stick out from the knuckles. If they're at rest, pointing out from the back of the hand, 
it's 0%. If they're rotated 90 degrees on the local X axis, so they jab forward over the fingers 
like Wolverine claws, it's 100%.

"Quick Pose" puts all of those to 90 degrees, and takes a guess at where the opposable thumbs should 
be positioned. The hands should now be fists, but the thumb positions often need a bit of manual 
(hah) tweaking in pose mode.

If you select another mesh object, then select the armature again so armature is active, you'll 
have options for "Grip Target R" and "Grip Target L." These actually set the targets of the 
constraints to that other mesh you have selected, so the hand can grab on properly. You can also 
set a different target later without having to run the initial setup again.

I'm going to add more options to fine-tune the "collision" results, but most of the time, the 
control bones will have all you need. Scaling them affects the offset of the shrinkwrap constraints
 and can help with a bit of clipping.

If you're sick of it and you want your old armature back, "Reset Hand R" and "Reset Hand L" clean up
after themselves pretty well, deleting everything this script did and leaving the original rig
untouched.
"""


import bpy
from bpy import context
import mathutils
import numpy as np
import math

# I put this prefix on all the constraints and such I make with this add-on,
# so that they're easy to locate and remove on a reset
prefix = "AutoGrip_"

# Bone collections that hold the control bones and the (hidden) projector bones
control_collection = "AutoGrip Controls"
projector_collection = "AutoGrip Projectors"


def move_to_collection(obj, bone, collection_name, visible):

    # Puts a bone in exactly one bone collection, creating the collection if needed

    collections = obj.data.collections
    target = collections.get(collection_name)
    if target is None:
        target = collections.new(collection_name)
    target.is_visible = visible
    for c in list(bone.collections):
        if c != target:
            c.unassign(bone)
    target.assign(bone)


makehuman_dictionary = {
        
    "palm_index.L": ["f_index.01.L", "f_index.02.L", "f_index.03.L"],
    "palm_middle.L": ["f_middle.01.L", "f_middle.02.L", "f_middle.03.L"],
    "palm_ring.L": ["f_ring.01.L", "f_ring.02.L", "f_ring.03.L"],
    "palm_pinky.L": ["f_pinky.01.L", "f_pinky.02.L", "f_pinky.03.L"],
        
    "palm_index.R": ["f_index.01.R", "f_index.02.R", "f_index.03.R"],
    "palm_middle.R": ["f_middle.01.R", "f_middle.02.R", "f_middle.03.R"],
    "palm_ring.R": ["f_ring.01.R", "f_ring.02.R", "f_ring.03.R"],
    "palm_pinky.R": ["f_pinky.01.R", "f_pinky.02.R", "f_pinky.03.R"],
        
        
    "thumb.01.L": ["thumb.02.L", "thumb.03.L"],
    "thumb.01.R": ["thumb.02.R", "thumb.03.R"]
}
    
rigify_dictionary = {
    "ORG-palm.01.L": ["f_index.01.L", "f_index.02.L", "f_index.03.L"],
    "ORG-palm.02.L": ["f_middle.01.L", "f_middle.02.L", "f_middle.03.L"],
    "ORG-palm.03.L": ["f_ring.01.L", "f_ring.02.L", "f_ring.03.L"],
    "ORG-palm.04.L": ["f_pinky.01.L", "f_pinky.02.L", "f_pinky.03.L"],
        
    "ORG-palm.01.R": ["f_index.01.R", "f_index.02.R", "f_index.03.R"],
    "ORG-palm.02.R": ["f_middle.01.R", "f_middle.02.R", "f_middle.03.R"],
    "ORG-palm.03.R": ["f_ring.01.R", "f_ring.02.R", "f_ring.03.R"],
    "ORG-palm.04.R": ["f_pinky.01.R", "f_pinky.02.R", "f_pinky.03.R"],
        
    "ORG-thumb.01.L": ["thumb.02.L", "thumb.03.L"],
    "ORG-thumb.01.R": ["thumb.02.R", "thumb.03.R"]
}
    

fps_dictionary = {
    "Bone_L.016": ["Bone_L.017", "Bone_L.018", "Bone_L.019"],
    "Bone_L.008": ["Bone_L.013", "Bone_L.014", "Bone_L.015"],
    "Bone_L.009": ["Bone_L.010", "Bone_L.011", "Bone_L.012"],
    "Bone_L.004": ["Bone_L.005", "Bone_L.006", "Bone_L.007"],
    "Bone_L.020": ["Bone_L.021", "Bone_L.022"],
    "Bone_R.016": ["Bone_R.017", "Bone_R.018", "Bone_R.019"],
    "Bone_R.008": ["Bone_R.013", "Bone_R.014", "Bone_R.015"],
    "Bone_R.009": ["Bone_R.010", "Bone_R.011", "Bone_R.012"],
    "Bone_R.004": ["Bone_R.005", "Bone_R.006", "Bone_R.007"],
    "Bone_R.020": ["Bone_R.021", "Bone_R.022"]
}

autorig_dictionary = {
    'c_index1_base.l': ['c_index1.l', 'c_index2.l', 'c_index3.l'],        
    'c_middle1_base.l': ['c_middle1.l', 'c_middle2.l', 'c_middle3.l'],        
    'c_ring1_base.l': ['c_ring1.l', 'c_ring2.l', 'c_ring3.l'],
    'c_pinky1_base.l': ['c_pinky1.l', 'c_pinky2.l', 'c_pinky3.l'],        
    'c_thumb1.l': ['c_thumb2.l', 'c_thumb3.l'],
        
    'c_index1_base.r': ['c_index1.r', 'c_index2.r', 'c_index3.r'],
    'c_middle1_base.r': ['c_middle1.r', 'c_middle2.r', 'c_middle3.r'],    
    'c_ring1_base.r': ['c_ring1.r', 'c_ring2.r', 'c_ring3.r'],        
    'c_pinky1_base.r': ['c_pinky1.r', 'c_pinky2.r', 'c_pinky3.r'],
    'c_thumb1.r': ['c_thumb2.r', 'c_thumb3.r'],
}

class fingerchain:
    obj = None
    phalanges = []
    control_bone = None
    axis = ''
    offset = 0.0
    projectors = [] 
    
    palmroot = None
    name = ''
    
    prop = None

    def __init__(self, obj, boneslist, axis='x', name="Default", offset = 0.0):   # Use X as bend axis by default, unless
                                               # set otherwise on initiation
        print("Finger created")
        self.obj = obj
        self.phalanges = boneslist
        self.axis = axis
        self.offset = offset
        self.palmroot = boneslist[0].parent
        self.name = name
        self.control_bone = None
        
        self.projectors = []
    
    def setup(self):    # Setup: calls the functions to create projectors, 
            # put IK constraints between phalanges and
                        # those projectors, and create control bone
        print("Setting up finger " + self.name)
        self.create_projectors()    
        self.constrain_IK()
        self.create_control()
    
    def view(self):
        print("\nFinger named " +self.name + ", of length " + str(len(self.phalanges)) + 
        ", starting bone " + self.phalanges[0].name, end = '')
        if self.axis!='':
            print(", axis = " + self.axis, end='')
        print(", root bone: " + self.palmroot.name)
        if len(self.projectors) > 0:
            print("Projectors: ")  
            for p in self.projectors[:]:
                print(p.name)
        else:
            print("No projectors established")
        if self.control_bone is None:
            print("No control bone established")
        else:
            print("Control bone is " + self.control_bone.name)
        if self.prop == None:
            print("No grip target established")
        else:
            print("Grip target: " + self.prop.name)
        print()
        
    def viewchain(self):
        print("bonechain of finger " + self.name)
        for f in self.phalanges:
            print(f.name, end=' ')
        print()
        
    def create_control(self):    
        # Creates control bone, does not rig up constraints for it
        
        # If it creates the control bones and tries to parent them to the hand when
        # the model is in a pose, they end up offset. Still function correctly,
        # but I'm putting it to rest position real quick to avoid that.
        prev_position = self.obj.data.pose_position
        self.obj.data.pose_position = 'REST'
        
        print("Creating control bone for finger " + self.name)
        
        palmroot_tail_loc = self.palmroot.tail       
        palmroot_name = self.palmroot.name
        #print("palmroot name is " + palmroot_name)
        
        postfix = palmroot_name[-1]
        
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        ebs = self.obj.data.edit_bones
        
        control = ebs.new("control_" + self.name + '.' + postfix)
        
        control.head = palmroot_tail_loc
        
        singlebone = self.palmroot
        axis = self.axis
        #print(axis)
        
        if type(axis) is str:
            #print("axis is string")
            if axis == '-x': 
                translation = singlebone.x_axis 
            elif axis == '-y':
                translation = singlebone.y_axis
            elif axis == '-z':
                translation = singlebone.z_axis
            elif axis == 'x':
                translation = - singlebone.x_axis 
            elif axis == 'y':
                translation = - singlebone.y_axis
            elif axis == 'z':
                translation = - singlebone.z_axis
        else:
            print("no valid control axis found")
            translation = (0.0, 0.0, 0.0)
            
        # It may be worth repeating the vector math to apply finger offset to this
    
        translation.length = singlebone.length  
        
        loc = control.head + mathutils.Vector(translation)

        control.tail = loc
        
        control.parent = name_to_editbone(self.obj, self.palmroot.name)
        
        control.use_deform = False
        
        control.align_roll(self.palmroot.y_axis)
        
        stringholder = control.name
        
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
        
        self.control_bone = name_to_posebone(self.obj, stringholder)
        
        self.obj.data.pose_position = prev_position
        
    def create_projectors(self):    
        # Creates projectors, does not set up constraints
         # Calls new_single_projector for each one
        print("creating projectors for finger " + self.name)
        
        created_list = []
        
        chain = self.phalanges
        palmroot = self.palmroot
        
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        ebs = self.obj.data.edit_bones
        
        editchain = []
        
        for posebone in chain[:]:
            namematch = name_to_editbone(self.obj, posebone.name)
            editchain.append(namematch)
            
        """
    print("full editbones chain: ")
        for printbone in editchain[:]:
            print(printbone.name, end=' ')
        print()
    """
        
        #print("looping projector creation")
        for phalange in editchain[:]:
            created_list.append(self.new_single_projector(ebs, phalange))
        
        nameslist = []
        for i in created_list:
            nameslist.append(i.name)
        
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
                
        for newprojector in nameslist:
            posematch = name_to_posebone(self.obj, newprojector)
            self.projectors.append(posematch)
            #print(newprojector + " added to " + self.name + " projectors list")
            
    def new_single_projector(self, editbones, singlebone):     
        #Creates a single projector off a
        # single phalange bone
        #Singlebone needs to be editbone
        
        axis = self.axis
        
        #print("creating projector off bone " + singlebone.name)
        first = editbones.new("projector_" + singlebone.name)
        
        if type(axis) is str:
            #print('axis is string')
            if axis == '-x':
                translation = - singlebone.x_axis 
            elif axis == '-y':
                translation = - singlebone.y_axis
            elif axis == '-z':
                translation = - singlebone.z_axis
            elif axis == 'x':
                translation = singlebone.x_axis 
            elif axis == 'y':
                translation = singlebone.y_axis
            elif axis == 'z':
                translation = singlebone.z_axis
        else:
            print("no valid finger axis found")
            translation = (0.0, 0.0, 0.0)
        
        if self.offset != 0:
            print(self.name + " has a set offset of " + str(self.offset) + " radians")
            translation = rotate_around(translation, singlebone.y_axis, self.offset)
            
        translation.length = singlebone.length  
        #print(translation) 
        
        loc = singlebone.head + mathutils.Vector(translation)
        #print(first.name + " loc: " + str(loc))
        first.head = loc
        first.tail = singlebone.tail
        first.parent = singlebone.parent
        first.length = first.length / 3
        first.use_deform = False
        
        return first
                
    def damped_track_projectors(self):   
        #Adds damped track modifiers to each projector, 
        # attaching them to the corresponding phalange
        
        print("adding damped track modifiers")
        for j in self.phalanges:
            for p in self.projectors:
                if j.name in p:
                    #print("projector " + p.name + " to fingerbone " + j.name)
                    fingertiplock = p.constraints.new("DAMPED_TRACK")
                    fingertiplock.target = self.obj
                    fingertiplock.subtarget = j.name
                    fingertiplock.head_tail = 1.0
                    fingertiplock.name = prefix + "Damped Track"
                    
    def add_shrinkwraps(self):
        # This creates shrinkwrap constraints on each projector, but DOESN'T set the target yet
        # Looks for the shrinkwrap modifier and then calls  create_single_shrinkwrap if not found
        print("creating shrinkwrap constraints for " + self.name)
        
        #self.prop = griptarget
        
        for q in self.projectors:
            found = False
            for c in q.constraints:
                #print(c.name)
                if 'hrinkwrap' in c.name:
                    found = True
                    break
            if not found:   
                create_single_shrinkwrap(q)
    
    def target_shrinkwraps(self, griptarget):
        
        # Sets the target of the shrinkwrap constraints to the target object
        
        for p in self.projectors:
            for c in p.constraints:
                if 'hrinkwrap' in c.name:
                    c.target = griptarget
    
        
    def constrain_IK(self):
        
        # Adds IK constraints to each phalange, linking them to the corresponding projector
        # Calls addIK with phalange and projector
        
        print("Linking IK constraints for finger " + self.name)
        
        for joint in self.phalanges:
            namestring = "projector_" + joint.name
            aim = self.obj.pose.bones[namestring]
            addIK(self.obj, joint, aim)
                
    def set_armature_layers(self):

        # Moves the projector bones and the control bone into their own bone collections.
        # Controls stay visible, projectors are hidden.

        move_to_collection(self.obj, self.control_bone.bone, control_collection, True)
        for joint in self.projectors:
            move_to_collection(self.obj, joint.bone, projector_collection, False)

    def reconstruct(self):
        obj = self.obj
        # When the finger already has a bonechain, finds projectors and control bone
        
        direction_char = self.palmroot.name[-1]
        
        print("Reconstructing finger " + self.name)
        
        if len(self.projectors) == 0:
            print("Relocate projectors:", end=' ')
            for i in self.palmroot.children_recursive:
                if "project" in i.name:
                    self.projectors.append(i)
            print(str(len(self.projectors)) + " projectors found")
        else:
            print((str(len(self.projectors))) + " projectors already linked")
            
        if self.control_bone == None:
            print("relocate control")
            stringcontrol = "control_" + self.name + '.' + direction_char
            try: 
                self.control_bone = self.obj.pose.bones[stringcontrol]
                print("found control bone, name " + self.control_bone.name)
                #break
            except:
                print("No control bone found for " + self.name)
                
        else:
            print("control bone already exists, name " + self.control_bone.name)
    
# These are honestly unnecessary but I thought I needed them at one point. Will clean it up
# to remove them later because they're literally one line
    
def name_to_editbone(obj, key):
    return obj.data.edit_bones[key]
def name_to_bone(obj, key):
    return obj.data.bones[key]
def name_to_posebone(obj, key):
    return obj.pose.bones[key]
    
    
def rotation_matrix(axis, theta):
    #This is from here https://stackoverflow.com/questions/6802577/rotation-of-3d-vector
    """
    Return the rotation matrix associated with counterclockwise rotation about
    the given axis by theta radians.
    """
    axis = np.asarray(axis)
    axis = axis / math.sqrt(np.dot(axis, axis))
    a = math.cos(theta / 2.0)
    b, c, d = -axis * math.sin(theta / 2.0)
    aa, bb, cc, dd = a * a, b * b, c * c, d * d
    bc, ad, ac, ab, bd, cd = b * c, a * d, a * c, a * b, b * d, c * d
    return np.array([[aa + bb - cc - dd, 2 * (bc + ad), 2 * (bd - ac)],
                     [2 * (bc - ad), aa + cc - bb - dd, 2 * (cd + ab)],
                     [2 * (bd + ac), 2 * (cd - ab), aa + dd - bb - cc]])

def rotate_around(source, rotationaxis, offset):
    
    # Calls rotation_matrix in a way that's useful to me
    
    arr = np.dot(rotation_matrix(rotationaxis, offset), source)
    vector_arr = mathutils.Vector(tuple(arr))
    return vector_arr    

def addIK(obj, posebone, target):
    
    #Hooks the designated posebone up with an IK constraint to the designated target,
    #with chain count set to 1 and iterations to 16 to keep down memory issues
    
    #print("adding IK to bone " + posebone.name)
    newIK = posebone.constraints.new("IK")
    newIK.chain_count = 1
    newIK.iterations = 16
    newIK.name = prefix + "IK"
    
    if type(posebone) == bpy.types.PoseBone:
        newIK.target = obj
        newIK.subtarget = target.name
    elif type(posebone) == bpy.types.Object:
        newIK.target = target

def create_single_shrinkwrap(projectorbone):
    
    # This adds the shrinkwrap constraints onto a pose bone, 
    # which should be a projector
    
    if type(projectorbone) is not bpy.types.PoseBone:
        print("!!! " + projectorbone.name + " is not pose bone")
        return
    newProject = projectorbone.constraints.new("SHRINKWRAP")
    newProject.shrinkwrap_type = "PROJECT"
    newProject.project_axis = "POS_Y"
    newProject.cull_face = "FRONT"    
    newProject.wrap_mode = "OUTSIDE_SURFACE"
    newProject.name = prefix + "shrinkwrap"
    
    #setting distance relative to bone length for the moment. Not perfect but it will do
    newProject.distance = 0.15 * projectorbone.length 
        
def assemble_hand(obj, handbone):
    
    # Puts likely finger bones together in chains, 
    # then makes basic fingers out of them. Most of the rewriting to let this work on 
    # other armatures happens here.
     
    # Returns a list of fingers
    
    rig_choice = obj.global_rig_choice

    fingerlist = []
    fingerroots = []
    
    print("Assembling hand off of " + handbone.name + ", with rig choice " + rig_choice)
    
    chosen_dictionary = {}
    
    if rig_choice == 'MHX':
        chosen_dictionary = makehuman_dictionary
    elif rig_choice == "RFY":
        chosen_dictionary = rigify_dictionary
    elif rig_choice == "ARP":
        chosen_dictionary = autorig_dictionary
    elif rig_choice == "FPS":
        chosen_dictionary = fps_dictionary
    elif rig_choice == "GEN":
        # Traverse children to find all chains ending in tip-bones. Filter for chains of length >= 2.
        chains = []
        def traverse(bone, current_chain):
            current_chain.append(bone)
            if not bone.children:
                if len(current_chain) >= 2:
                    chains.append(list(current_chain))
            else:
                for child in bone.children:
                    if prefix not in child.name and not child.name.startswith("control_") and not child.name.startswith("projector_"):
                        traverse(child, current_chain)
            current_chain.pop()
        
        for child in handbone.children:
            traverse(child, [])
            
        # Sort chains by relative Y or X coordinates.
        # We can use the root of each chain's head_local position relative to the handbone
        # Actually, sorting by `head_local.y` or `head_local.x`. Wait, we just sort by their head_local position relative to the handbone.
        def get_local_coord(bone):
            # handbone matrix is in armature space.
            # handbone.matrix.inverted() @ bone.head
            return (handbone.matrix.inverted() @ bone[0].head).x
        chains.sort(key=get_local_coord)
        
        chosen_dictionary = {}
        for chain in chains:
            root_name = chain[0].name
            chosen_dictionary[root_name] = [b.name for b in chain[1:]]

    print("choice = " + rig_choice)
    direction = handbone.name[-1]
    
    for key in chosen_dictionary:
        if key.endswith(direction) or f"_{direction}" in key or f".{direction}" in key or rig_choice == 'GEN':
            print("# " + key)
            if key in obj.pose.bones:
                fingerroots.append(obj.pose.bones[key])
            else:
                print(f"Warning: {key} not found in bones")
    # And then THIS assembles the fingers off each palm. I've got a dictionary set up 
    # that tells it the whole list of fingers it should be looking for for 
    # each rig type. Elegant? No. Fast? Yes
    
    # Now that I've got all 3 options using a dictionary, I should probably
    # merge more of these into one function
    
    for loop_palm in fingerroots:
        try:
            print()
            newfinger = None
            bonechain = []
            
            nameslist = chosen_dictionary[loop_palm.name]

            for j in nameslist:
                print(j, end=', ')
                bonechain.append(obj.pose.bones[j])
                
            if rig_choice == 'ARP':
                rootname = loop_palm.name
                fingername = rootname.split('_')[1]
                fingername = fingername[:-1]
            else:
                if rig_choice == 'GEN':
                    fingername = bonechain[0].name
                else:
                    fingername = bonechain[0].basename
                
            
            if 'thumb' in fingername:
                if rig_choice == 'MHX':
                    if bonechain[0].name == "thumb.02.L":
                        print("\nCREATING LEFT MAKEHUMAN THUMB")
                        newfinger = fingerchain(obj, bonechain, 'z', fingername, 0.8)
                    elif bonechain[0].name ==  "thumb.02.R":
                        print("\nCREATING RIGHT MAKEHUMAN THUMB")
                        newfinger = fingerchain(obj, bonechain, 'z', fingername, -0.8)
                elif rig_choice == 'RFY':
                    if bonechain[0].name == "thumb.02.L":
                        print("\nCREATING LEFT RIGIFY THUMB")
                        newfinger = fingerchain(obj, bonechain, 'z', fingername, -0.7)
                    elif bonechain[0].name ==  "thumb.02.R":
                        print("\nCREATING RIGHT RIGIFY THUMB")
                        newfinger = fingerchain(obj, bonechain, 'z', fingername, 0.7)
                elif rig_choice == 'ARP':
                    print("\nCREATING AUTORIG THUMB")
                    newfinger = fingerchain(obj, bonechain, '-z', fingername)
                elif rig_choice in ('FPS', 'GEN'):
                    print("\nCREATING FPS/GEN THUMB")
                    newfinger = fingerchain(obj, bonechain, 'z', fingername)
                    
            else:
                print("creating other finger")
                if rig_choice == 'ARP':
                    newfinger = fingerchain(obj, bonechain, '-z', fingername)
                else:
                    newfinger = fingerchain(obj, bonechain, 'z', fingername)
            
            if newfinger is None:
                raise RuntimeError("no finger created")
            fingerlist.append(newfinger)
        except Exception as e:
            print("\n", loop_palm.name, "FINGER NOT FOUND:", repr(e))
        
    return fingerlist

def control_drivers(obj, finger):
    
    # Puts rotation limits on control bone, then hooks up the influence of all those IK constraints
    # to depend on control bone rotation. Maybe the rotation limit part should be somewhere else
    
    finger.control_bone.rotation_mode = "XYZ"
    
    print("\nApplying rotation limits to " + finger.name + " control bone")
    rotationlock = finger.control_bone.constraints.new("LIMIT_ROTATION")
    rotationlock.owner_space = "LOCAL"
    rotationlock.name = prefix + "Rotation Limit"
    rotationlock.use_limit_x = True
    rotationlock.max_x = 3.14159 / 2
    rotationlock.use_limit_y = True
    rotationlock.use_limit_z = True
    
    print("Applying angle drivers")
    for joint in finger.phalanges:
        #print('driver for bone ' + joint.name)
        driver = obj.driver_add('pose.bones["' + joint.name + '"].constraints["' + prefix + 'IK"].influence').driver 
        v = driver.variables.new()
        v.name = 'gripcontrol'
        
        v.targets[0].id        = obj
        v.targets[0].data_path = 'pose.bones["' + finger.control_bone.name + '"].rotation_euler[0]'
        
        driver.expression = v.name + " * 0.637"
        
    print("Applying scale drivers")
    for p in finger.projectors:
        #print(p.name)
        stringholder = p.name
        scaledriver = obj.driver_add('pose.bones["' + stringholder + '"].constraints["' + prefix 
        + 'shrinkwrap"].distance').driver
        v = scaledriver.variables.new()
        v.name = 'gripscale'
        
        v.targets[0].id = obj
        v.targets[0].data_path = 'pose.bones["' + finger.control_bone.name + '"].scale[0]'
        
        # Offset stays relative to the projector's length, same as create_single_shrinkwrap
        scaledriver.expression = v.name + " * " + repr(0.15 * p.length)

def find_hand_root(obj, direction):
    
    rig_choice = obj.global_rig_choice

    try:
        if rig_choice == 'MHX':
            if direction.lower() == 'l':
                return obj.pose.bones['hand0.L']
            elif direction.lower() == 'r':
                return obj.pose.bones['hand0.R']
        elif rig_choice == 'RFY':
            if direction.lower() == 'l':
                return obj.pose.bones['DEF-hand.L']
            elif direction.lower() == 'r':
                return obj.pose.bones['DEF-hand.R']
        elif rig_choice == 'ARP':
            if direction.lower() == 'r':
                return obj.pose.bones['hand.r']
            elif direction.lower() == 'l':
                return obj.pose.bones['hand.l']
        elif rig_choice == 'GEN':
            for pb in obj.pose.bones:
                if 'hand' in pb.name.lower() and not any(sub in pb.name.lower() for sub in ['ik', 'ctrl', 'cntrl', 'target', 'pole']):
                    if pb.name.endswith(direction) or f"_{direction}" in pb.name or f".{direction}" in pb.name or f" {direction}" in pb.name:
                        return pb
        elif rig_choice == 'FPS':
            if direction.lower() == 'l':
                return obj.pose.bones['Hand L']
            elif direction.lower() == 'r':
                return obj.pose.bones['Hand R']
    except:
        # I'm trying to figure out how to report a more elegant error to the user if they're
        # on the wrong rig, without them needing to have open a console view. This is
        # not ideal but it'll take more research.
        
        raise RuntimeError("Couldn't find hand root. Are you sure you have the right rig type?")

def setup_hand(obj, targetroot):
    
    # Takes a root hand bone, calls assemble_hand to get a list of fingers out of it
    # Then runs setup(), damped_track_projectors(), control_drivers(), and add_shrinkwraps()
    # on each one
    
    # Needs to run control_drivers after add_shrinkwraps
    
    fingers_list = assemble_hand(obj, targetroot)
         
    for finger in fingers_list:
        finger.setup()
        finger.damped_track_projectors()
        finger.add_shrinkwraps()
        control_drivers(obj, finger)
        finger.set_armature_layers()

def _run_api(operator, context, call):
    
    # Operators are thin wrappers over api.py. Errors from the api become UI error reports.
    
    from . import api
    try:
        call(api, context.active_object)
    except (RuntimeError, ValueError) as e:
        operator.report({'ERROR'}, str(e))
        return {'CANCELLED'}
    return {'FINISHED'}

def _selected_target(context):
    
    # First selected object that isn't the active armature
    
    for t in context.selected_objects:
        if t != context.active_object:
            return t
    return None


class AutoGripFixRolls(bpy.types.Operator):
    """Fix Bone Rolls for Fingers"""
    bl_idname = "object.autogrip_fix_rolls"
    bl_label = "Fix Bone Rolls"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return _run_api(self, context, lambda api, arm: api.fix_bone_rolls(arm, 'BOTH'))

class AutoGripSetup(bpy.types.Operator):
    """Set up AutoGrip rig"""
    bl_idname = "object.autogrip_setup"
    bl_label = "AutoGrip Setup"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return _run_api(self, context, lambda api, arm: api.setup(arm, 'BOTH', arm.global_rig_choice))
            
            
class AutoGripLeft(bpy.types.Operator):
    """Set up AutoGrip rig for left hand only"""
    bl_idname = "object.autogrip_setup_left"
    bl_label = "Setup Left"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return _run_api(self, context, lambda api, arm: api.setup(arm, 'L', arm.global_rig_choice))
            
class AutoGripRight(bpy.types.Operator):
    """Set up AutoGrip rig for right hand only"""
    bl_idname = "object.autogrip_setup_right"
    bl_label = "Setup Right"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return _run_api(self, context, lambda api, arm: api.setup(arm, 'R', arm.global_rig_choice))
            
class TargetLeft(bpy.types.Operator):
    """Set Grip Target for left hand"""
    bl_idname = "object.autogrip_target_l"
    bl_label = "Grip Target L"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        target = _selected_target(context)
        if target is None:
            self.report({'ERROR'}, "Select the target mesh as well as the armature.")
            return {'CANCELLED'}
        return _run_api(self, context, lambda api, arm: api.set_target(arm, target, 'L'))
    
class TargetRight(bpy.types.Operator):
    """Set Grip Target for right hand"""
    bl_idname = "object.autogrip_target_r"
    bl_label = "Grip Target R"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        target = _selected_target(context)
        if target is None:
            self.report({'ERROR'}, "Select the target mesh as well as the armature.")
            return {'CANCELLED'}
        return _run_api(self, context, lambda api, arm: api.set_target(arm, target, 'R'))


def reset_hand(obj, wristroot, reset_pose=True):
    
    
    fingers_list = assemble_hand(obj, wristroot)
    for f in fingers_list:
        f.reconstruct()
    
    print("removing constraints")
    
    for f in fingers_list:
            for p in f.phalanges:
                for c in list(p.constraints):
                    if prefix in c.name:
                        obj.driver_remove('pose.bones["' + p.name + '"].constraints["' + c.name + '"].influence')
                        p.constraints.remove(c)   
            for j in f.projectors:
                for c in list(j.constraints):
                    if prefix in c.name:
                        obj.driver_remove('pose.bones["' + j.name + '"].constraints["' + c.name + '"].distance')
                        # No point in removing the constraint because I'll delete the whole bone
            
            if reset_pose:
                # Quick Pose and grip rotate the phalanges and the thumb root, so put those back
                posed = list(f.phalanges)
                if 'thumb' in f.name:
                    posed.append(f.palmroot)
                for pb in posed:
                    pb.rotation_euler = (0.0, 0.0, 0.0)
                    pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
                        
    print('entering edit mode')
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    
    ebs = obj.data.edit_bones
    
    print("deleting projectors")
    for f in fingers_list:
        for j in f.projectors:
            try:
                projectorname = j.name
                ebs.remove(ebs[projectorname])
            except Exception as e:
                print("!!! failed to delete projector:", repr(e))
        
    print("deleting control bones")
    for f in fingers_list:
        if f.control_bone == None:
            print(f.name + " has no control bone")
            continue
        try:
            controlname = f.control_bone.name
            ebs.remove(ebs[controlname])
        except Exception as e:
            print("!!! failed to delete control bone:", repr(e))
    
    print('entering object mode')
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)       
    
class ResetHandLeft(bpy.types.Operator):
    """Reset all autogrip stuff on left hand"""
    bl_idname = "object.autogrip_reset_l"
    bl_label = "Reset Hand L"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return _run_api(self, context, lambda api, arm: api.reset(arm, 'L'))
    
class ResetHandRight(bpy.types.Operator):
    """Reset all autogrip stuff on right hand"""
    bl_idname = "object.autogrip_reset_r"
    bl_label = "Reset Hand R"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return _run_api(self, context, lambda api, arm: api.reset(arm, 'R'))

# Thumb positions used by Quick Pose, per rig type: (bone name or prefix, left values, right values).
# MHX and ARP use euler rotation, Rigify uses quaternions.
thumb_presets = {
    'MHX': ('thumb.01.{}', (0.43, 0.27, 0.32), (0.43, -0.27, -0.17)),
    'RFY': ('ORG-thumb.01', (0.85, -0.114, 0.36, 0.36), (0.85, -0.114, -0.36, -0.36)),
    'ARP': ('c_thumb1_base.{}', (1.62, 0, -0.3), (1.62, 0, 0.3)),
}

def apply_thumb_preset(obj, handroot, direction):
    
    # Guesses an opposable thumb position for the hand under handroot
    
    rig_choice = obj.global_rig_choice
    if rig_choice not in thumb_presets:
        return
    name, left, right = thumb_presets[rig_choice]
    if rig_choice == 'ARP':
        name = name.format(direction.lower())
    else:
        name = name.format(direction.upper())
    values = left if direction.upper() == 'L' else right
    
    for bone in handroot.children_recursive:
        matches = (bone.name == name) if rig_choice == 'ARP' else (name in bone.name)
        if matches:
            if rig_choice == 'RFY':
                bone.rotation_mode = 'QUATERNION'
                bone.rotation_quaternion = values
            else:
                bone.rotation_mode = 'XYZ'
                bone.rotation_euler = values

def close_hand_fully(obj, direction, thumb=True):
    
    # Quick Pose for one hand: every control bone to 90 degrees, plus the thumb guess
    
    handroot = find_hand_root(obj, direction)
    for bone in handroot.children_recursive:
        if 'control' in bone.name:
            bone.rotation_euler[0] = math.pi / 2
    if thumb:
        apply_thumb_preset(obj, handroot, direction)

class QuickPose(bpy.types.Operator):
    """Quickly put all control bones to active position"""
    bl_idname = "object.autogrip_quickpose"
    bl_label = "Quick Pose"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return _run_api(self, context, lambda api, arm: api.quick_pose(arm, 'BOTH'))
        
class github_link(bpy.types.Operator):
    
    """Check this out for updates or to report any issues you find"""
    bl_idname = "object.autogrip_discussion_link"
    bl_label = "Github Link"
    
    def execute(self, context):
        
        import webbrowser
        webbrowser.open("https://github.com/Jetpack-Crow/autogrip")  
        
        return {'FINISHED'}
    
class kofi_link(bpy.types.Operator):
    
    """Donate a dollar or two?"""
    bl_idname = "object.kofi_link"
    bl_label = "Tip Jar"
    
    def execute(self, context):
        
        import webbrowser
        webbrowser.open("https://ko-fi.com/jetpackcrow")  
        
        return {'FINISHED'}
    
def bone_in_armature(key):  # This function is used only for rig guessing.
    try:
        print(obj.pose.bones[key].name, "found in armature")
        return True
    except:
        print(key + " not found in armature")
        return False

class guess_rig_type(bpy.types.Operator):
    """Check if rig is compatible with any of the precoded types."""
    
    bl_idname = "object.autogrip_guess_rig"
    bl_label = "Guess Rig Type"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        
        obj = bpy.context.active_object
        activeArmature = bpy.context.active_object.data
        
        print("guessing rig type for", obj.name)
        
        dictionaries_list = [makehuman_dictionary, rigify_dictionary, autorig_dictionary, fps_dictionary]
        type_names_list = ['MHX', 'RFY', 'ARP', 'FPS']
        
        rig_type = None
        
        message = "Rig doesn't match precoded types."
        
        for type in dictionaries_list:
            match = True
            
            # There has to be a better way to get the corresponding name than this.
            # But it's what I got for now. TODO
            
            dictionary_index = dictionaries_list.index(type)
            
            rig_type = type_names_list[dictionary_index]
            
            for key in type:
                if bone_in_armature(key):
                    continue
                else:
                    print("Armature cannot be " + rig_type)
                    match = False
                    break
            if match:
                
                obj.global_rig_choice = rig_type
                
                message = "Rig type: " + rig_type
                break
        
        self.report({'INFO'}, message)
    
        return {'FINISHED'}

        
class PANEL_PT_Autogrip(bpy.types.Panel):
    """Creates a sub tab in the N-panel"""
    bl_label = "AutoGrip Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AutoGrip"
    #bl_context = "objectmode"
    
    def draw(self, context):
        obj = context.active_object 
        
        layout = self.layout
        
        
        try:
            activeArmature = obj.data
                
            target = None
            for t in bpy.context.selected_objects:
                if t != obj and type(t.data) is bpy.types.Mesh:
                    target = t
                    break
            

        except:
            row = layout.row()
            row.label(text="No active object.")
            
            row = layout.row()
            row.label(text="Links (Open in browser)")
            
            row = layout.row()
            row.operator(github_link.bl_idname)
            row.operator(kofi_link.bl_idname)

        
        """Provide setup options only if armature selected, provide target options only
        if there is a valid target to attach them to."""
        
        if type(activeArmature) is bpy.types.Armature:
            
            row = layout.row()
            row.label(text="Active armature: {}".format(activeArmature.name))
            
            row = layout.row()
            #row.label(text = "enum choice")
            row.prop(obj, "global_rig_choice")
            
            row = layout.row()
            row.operator(guess_rig_type.bl_idname)
            
            row = layout.row()
            
            row = layout.row()
            row.operator(AutoGripSetup.bl_idname)
            
            setuprow = layout.row()
            setupright = setuprow.operator(AutoGripRight.bl_idname)
            setupleft = setuprow.operator(AutoGripLeft.bl_idname)
            
            QProw = layout.row()
            QProw.operator(QuickPose.bl_idname)
            
            resetrow = layout.row()
            resetrow.operator(ResetHandRight.bl_idname)
            resetrow.operator(ResetHandLeft.bl_idname)
            
            if (target is not None) and (type(target.data) is bpy.types.Mesh):
                row = layout.row()
                row.label(text = "Target object: {}".format(target.name))
                
                row = layout.row()
                row.operator(TargetRight.bl_idname)
                row.operator(TargetLeft.bl_idname)
                
                row = layout.row()
                row.operator(AutoGripFixRolls.bl_idname)
        else:
            row = layout.row()
            row.label(text = "Active object is not armature.")   
        
            
        row = layout.row()
        row = layout.row()
        row.label(text="Links (Open in browser)")
        
        row = layout.row()
        row.operator(github_link.bl_idname)
        row.operator(kofi_link.bl_idname)

                       
        
classes = [AutoGripFixRolls, AutoGripSetup, AutoGripLeft, AutoGripRight, TargetRight, TargetLeft,
    ResetHandLeft, ResetHandRight, QuickPose, PANEL_PT_Autogrip, github_link, guess_rig_type,
    kofi_link]        
        
def register():
    
    # This just iterates over all the classes I defined and sets each one up, 
    # then creates the global_rig_choice enum that I'm gonna need. A rough copy of that
    # is also defined in each other function that needs it because "global" isn't as 
    # elegant as you would think here.
    
    print('\n~~~~~~~~~~~~registering setup~~~~~~~~~~~~\n')
    
    for item in classes:
        bpy.utils.register_class(item)
    
    bpy.types.Object.global_rig_choice = bpy.props.EnumProperty(
        name="Rig selection",
        description="Select an option",
        
        items = [ 
            ('MHX', "MHX", "MakeHuman Exchange"),
            ('RFY', "Rigify", "Modular armature from the Rigify add-on"),
            ('ARP', "Auto-Rig Pro", "Armature from the Auto-Rig Pro add-on"),
            ('FPS', "FPS Hands", "FPS Hands Rigged"),
            ('GEN', "Generic", "Auto-detected generic hand")
        ]
    )


def unregister():
    
    for item in classes:
        bpy.utils.unregister_class(item)
        
    del bpy.types.Object.global_rig_choice
    
    
if __name__ == "__main__":
    register()
    #unregister()