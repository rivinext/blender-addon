bl_info = {
    "name": "Voxel adjust Tools - Unified",
    "author": "Your Name / Code Copilot / Rivi",
    "version": (1, 1),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Voxel adjust",
    "description": ("OBJインポート、Merge By Distance、Pivot/Offset操作、\n"
                    "Vertex Group作成、均等配置、\n"
                    "Set Pivot and Move to Curve Point機能をひとつのパネルに統合"),
    "category": "matome",
}

import bpy
import bmesh
import re
from mathutils import Vector
from bpy.props import EnumProperty, FloatProperty, StringProperty

# ========================================================
# 1. 既存機能：OBJインポート、Merge By Distance
# ========================================================

# ---------- OBJインポート（修正版）----------
class OBJECT_OT_import_obj(bpy.types.Operator):
    """OBJファイルをインポート"""
    bl_idname = "object.import_obj_one_click"
    bl_label = "Import OBJ"

    filepath: StringProperty(
        name="OBJ File Path",
        description="パスを指定してください",
        subtype='FILE_PATH'
    )

    def execute(self, context):
        try:
            bpy.ops.import_scene.obj(filepath=self.filepath)
        except Exception as e:
            self.report({'ERROR'}, f"OBJファイルのインポートに失敗しました: {e}")
            return {'CANCELLED'}
        self.report({'INFO'}, "OBJファイルを正常にインポートしました")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

# ---------- Merge By Distance (redistance.pyの内容に入れ替え) ----------
class OBJECT_OT_merge_by_distance_operator(bpy.types.Operator):
    """Mark Sharp and Merge Vertices by Distance for selected objects"""
    bl_idname = "object.merge_by_distance_operator"
    bl_label = "Merge By Distance"
    bl_options = {'REGISTER', 'UNDO'}

    merge_distance: FloatProperty(
        name="Merge Distance",
        description="Maximum distance between vertices to be merged",
        default=0.01,
        min=0.00001,
        max=1.0,
        precision=5
    )

    def execute(self, context):
        selected_objects = context.selected_objects
        active_object = context.active_object

        if not selected_objects:
            self.report({'ERROR'}, "No objects selected")
            return {'CANCELLED'}

        # Store original mode and selection
        original_mode = context.mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Process each selected object
        for obj in selected_objects:
            if obj.type != 'MESH':
                continue

            # Make the current object active
            context.view_layer.objects.active = obj

            # Enter edit mode
            bpy.ops.object.mode_set(mode='EDIT')

            # Select all edges
            bpy.ops.mesh.select_all(action='SELECT')

            # Mark Sharp
            bpy.ops.mesh.mark_sharp()

            # Merge vertices by distance
            bpy.ops.mesh.remove_doubles(threshold=self.merge_distance)

            # Return to object mode
            bpy.ops.object.mode_set(mode='OBJECT')

        # Restore original active object
        context.view_layer.objects.active = active_object

        # Return to the original mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=original_mode)

        self.report({'INFO'}, f"Processed {len(selected_objects)} objects")
        return {'FINISHED'}

# ========================================================
# 2. 新機能：Set Pivot and Move to Curve Point
# （Merge By Distanceの直後に配置）
# ========================================================

class OBJECT_OT_SetPivotToSelectionCenter(bpy.types.Operator):
    bl_idname = "object.set_pivot_to_selection_center"
    bl_label = "Pivot to Selection Center"
    bl_description = ("Edit Modeの場合は選択した頂点/エッジ/面の中心へ、"
                      "Object Modeの場合はオブジェクト中心へピボットを移動")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.object is not None and context.object.type == 'MESH')

    def execute(self, context):
        obj = context.object
        if obj.mode == 'EDIT':
            me = obj.data
            bm = bmesh.from_edit_mesh(me)
            selected_coords = []
            # 選択頂点の座標
            selected_coords.extend([v.co for v in bm.verts if v.select])
            # 選択エッジの中点
            for edge in bm.edges:
                if edge.select:
                    edge_center = (edge.verts[0].co + edge.verts[1].co) / 2
                    selected_coords.append(edge_center)
            # 選択面の中心
            for face in bm.faces:
                if face.select:
                    face_center = face.calc_center_median()
                    selected_coords.append(face_center)
            if not selected_coords:
                bpy.ops.object.mode_set(mode='OBJECT')
                bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS', center='BOUNDS')
                bpy.ops.object.mode_set(mode='EDIT')
            else:
                center = sum(selected_coords, Vector()) / len(selected_coords)
                context.scene.cursor.location = obj.matrix_world @ center
                bpy.ops.object.mode_set(mode='OBJECT')
                bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
                bpy.ops.object.mode_set(mode='EDIT')
        else:
            # Object Modeの場合、各オブジェクトごとに処理
            selected_objects = context.selected_objects
            for obj in selected_objects:
                if obj.type == 'MESH':
                    me = obj.data
                    bm = bmesh.new()
                    bm.from_mesh(me)
                    all_coords = [v.co for v in bm.verts]
                    for edge in bm.edges:
                        edge_center = (edge.verts[0].co + edge.verts[1].co) / 2
                        all_coords.append(edge_center)
                    if all_coords:
                        center = sum(all_coords, Vector()) / len(all_coords)
                        context.scene.cursor.location = obj.matrix_world @ center
                        bpy.ops.object.select_all(action='DESELECT')
                        obj.select_set(True)
                        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
                    bm.free()
            # 再度全オブジェクトを選択
            for obj in context.selected_objects:
                obj.select_set(True)
        # 3Dカーソルをワールド原点にリセット
        context.scene.cursor.location = (0, 0, 0)
        return {'FINISHED'}

class OBJECT_OT_MovePivotToCurvePoint(bpy.types.Operator):
    bl_idname = "object.move_pivot_to_curve_point"
    bl_label = "Move Pivot to Curve Point"
    bl_description = "選択されたカーブの制御点に最も近い位置へピボットを移動"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        bpy.ops.object.mode_set(mode='OBJECT')
        selected_point = None
        # カーブ内の各スプラインのベジェポイントをチェック
        for spline in obj.data.splines:
            for point in spline.bezier_points:
                if point.select_control_point:
                    selected_point = point
                    break
            if selected_point:
                break
        if selected_point:
            context.scene.cursor.location = obj.matrix_world @ selected_point.co
            context.scene.tool_settings.transform_pivot_point = 'CURSOR'
            bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
            context.scene.cursor.location = (0.0, 0.0, 0.0)
        bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}

class OBJECT_OT_MoveSelectedObjectsToOrigin(bpy.types.Operator):
    bl_idname = "object.move_selected_objects_to_origin"
    bl_label = "Move Selected Objects to Origin"
    bl_description = "選択オブジェクトの位置をワールド原点(0,0,0)に移動"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for obj in context.selected_objects:
            obj.location = (0.0, 0.0, 0.0)
        return {'FINISHED'}

# ========================================================
# 3. 既存機能：Set Pivot (Extreme)およびVertex Group作成
# ========================================================

# ---------- Set Pivot (Extreme) ----------
class OBJECT_OT_set_pivot(bpy.types.Operator):
    """選択オブジェクトのPivotを極端な面に設定"""
    bl_idname = "object.set_pivot"
    bl_label = "Set Pivot (Extreme)"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(
        name="Axis",
        description="Pivotの移動方向を選択",
        items=[
            ('+X', "+X", "極端な+XにPivotを設定"),
            ('-X', "-X", "極端な-XにPivotを設定"),
            ('+Y', "+Y", "極端な+YにPivotを設定"),
            ('-Y', "-Y", "極端な-YにPivotを設定"),
            ('+Z', "+Z", "極端な+ZにPivotを設定"),
            ('-Z', "-Z", "極端な-ZにPivotを設定"),
        ]
    )

    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_objects:
            self.report({'ERROR'}, "メッシュオブジェクトを選択してください")
            return {'CANCELLED'}
        for obj in selected_objects:
            bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            if self.axis == '+X':
                target_points = [v for v in bbox if v.x == max(c.x for c in bbox)]
            elif self.axis == '-X':
                target_points = [v for v in bbox if v.x == min(c.x for c in bbox)]
            elif self.axis == '+Y':
                target_points = [v for v in bbox if v.y == max(c.y for c in bbox)]
            elif self.axis == '-Y':
                target_points = [v for v in bbox if v.y == min(c.y for c in bbox)]
            elif self.axis == '+Z':
                target_points = [v for v in bbox if v.z == max(c.z for c in bbox)]
            elif self.axis == '-Z':
                target_points = [v for v in bbox if v.z == min(c.z for c in bbox)]
            else:
                continue
            center = sum(target_points, Vector()) / len(target_points)
            context.scene.cursor.location = center
            prev_sel = [o for o in context.selected_objects]
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
            for o in prev_sel:
                o.select_set(True)
        self.report({'INFO'}, f"選択オブジェクトのPivotを{self.axis}側に設定しました")
        return {'FINISHED'}

# ---------- Vertex Group from Object Name ----------
def sanitize_name(name):
    sanitized_name = re.sub(r"\.\d+$", "", name)
    return sanitized_name

class OBJECT_OT_CreateVertexGroups(bpy.types.Operator):
    bl_idname = "object.create_vertex_groups"
    bl_label = "Create Vertex Groups"
    bl_description = "オブジェクト名からVertex Groupを作成し、全頂点を割り当てます"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_objects:
            self.report({'ERROR'}, "少なくとも1つのメッシュオブジェクトを選択してください")
            return {'CANCELLED'}
        for obj in selected_objects:
            group_name = sanitize_name(obj.name)
            context.view_layer.objects.active = obj
            if group_name not in obj.vertex_groups:
                vertex_group = obj.vertex_groups.new(name=group_name)
                all_verts = [v.index for v in obj.data.vertices]
                vertex_group.add(all_verts, 1.0, 'REPLACE')
                self.report({'INFO'}, f"Vertex group '{group_name}' created for object '{obj.name}'")
            else:
                self.report({'INFO'}, f"Vertex group '{group_name}' already exists in object '{obj.name}'")
        return {'FINISHED'}

# ========================================================
# 4. 既存機能：Unified Pivot and Offset Tool
# ========================================================

# --- ユーティリティ関数 ---
def set_pivot_to_extreme(obj, axis):
    bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    if axis == '+X':
        target_points = [v for v in bbox if v.x == max(c.x for c in bbox)]
    elif axis == '-X':
        target_points = [v for v in bbox if v.x == min(c.x for c in bbox)]
    elif axis == '+Y':
        target_points = [v for v in bbox if v.y == max(c.y for c in bbox)]
    elif axis == '-Y':
        target_points = [v for v in bbox if v.y == min(c.y for c in bbox)]
    elif axis == '+Z':
        target_points = [v for v in bbox if v.z == max(c.z for c in bbox)]
    elif axis == '-Z':
        target_points = [v for v in bbox if v.z == min(c.z for c in bbox)]
    else:
        return None
    center = sum(target_points, Vector()) / len(target_points)
    bpy.context.scene.cursor.location = center
    previous_selection = [o for o in bpy.context.selected_objects]
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    for ob in previous_selection:
        ob.select_set(True)

# --- Operator: Pivot Mover ---
class OBJECT_OT_PivotMover(bpy.types.Operator):
    bl_idname = "object.pivot_mover"
    bl_label = "Pivot Move"
    bl_description = "指定方向の極端な面の中心にPivotを移動"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(
        name="Axis",
        description="Pivotを移動する方向を選択",
        items=[
            ('+X', "+X", "Move pivot to the extreme +X"),
            ('-X', "-X", "Move pivot to the extreme -X"),
            ('+Y', "+Y", "Move pivot to the extreme +Y"),
            ('-Y', "-Y", "Move pivot to the extreme -Y"),
            ('+Z', "+Z", "Move pivot to the extreme +Z"),
            ('-Z', "-Z", "Move pivot to the extreme -Z"),
        ]
    )

    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_objects:
            self.report({'ERROR'}, "メッシュオブジェクトを選択してください")
            return {'CANCELLED'}
        for obj in selected_objects:
            set_pivot_to_extreme(obj, self.axis)
        bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
        self.report({'INFO'}, f"Pivot moved to {self.axis} side for selected objects")
        return {'FINISHED'}

# --- Operator: Set Axis and Apply Offset ---
class OBJECT_OT_SetAxisAndMove(bpy.types.Operator):
    """Set axis and move origin"""
    bl_idname = "object.set_axis_and_move"
    bl_label = "Set Axis and Apply Offset"
    bl_description = "指定方向へオフセットを適用して原点（Pivot）を移動"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(
        name="Axis",
        description="オフセット適用方向",
        items=[
            ('+X', "+X", "正のX方向へ移動"),
            ('-X', "-X", "負のX方向へ移動"),
            ('+Y', "+Y", "正のY方向へ移動"),
            ('-Y', "-Y", "負のY方向へ移動"),
            ('+Z', "+Z", "正のZ方向へ移動"),
            ('-Z', "-Z", "負のZ方向へ移動")
        ]
    )

    def execute(self, context):
        axis = self.axis
        offset = context.scene.move_origin_offset
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'WARNING'}, "オブジェクトが選択されていません")
            return {'CANCELLED'}
        for obj in selected_objects:
            if obj.type == 'MESH':
                context.view_layer.objects.active = obj
                original_cursor_location = context.scene.cursor.location.copy()
                origin = obj.matrix_world.translation.copy()
                if axis == '+X':
                    origin.x += offset
                elif axis == '-X':
                    origin.x -= offset
                elif axis == '+Y':
                    origin.y += offset
                elif axis == '-Y':
                    origin.y -= offset
                elif axis == '+Z':
                    origin.z += offset
                elif axis == '-Z':
                    origin.z -= offset
                context.scene.cursor.location = origin
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
                context.scene.cursor.location = original_cursor_location
        for obj in selected_objects:
            obj.select_set(True)
        self.report({'INFO'}, f"Offset applied along {axis} by {offset}m")
        return {'FINISHED'}

# ========================================================
# 5. 既存機能：Evenly Distribute Objects
# ========================================================

# ---------- 1) Distribute Between Min and Max ----------
class OBJECT_OT_evenly_distribute(bpy.types.Operator):
    """選択オブジェクトを、指定軸上の最小～最大の範囲に均等配置"""
    bl_idname = "object.evenly_distribute"
    bl_label = "Distribute (Min to Max)"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(
        name="Axis",
        description="配置する軸を選択",
        items=[
            ('X', "X", "X軸に沿って均等配置"),
            ('Y', "Y", "Y軸に沿って均等配置"),
            ('Z', "Z", "Z軸に沿って均等配置"),
        ],
        default='X'
    )

    def execute(self, context):
        selected_objs = [obj for obj in context.selected_objects if obj.type in {'MESH', 'ARMATURE'}]
        if len(selected_objs) < 2:
            self.report({'WARNING'}, "2つ以上のオブジェクト（MESHまたはARMATURE）を選択してください。")
            return {'CANCELLED'}
        if self.axis == 'X':
            selected_objs.sort(key=lambda o: o.location.x)
            min_val = selected_objs[0].location.x
            max_val = selected_objs[-1].location.x
        elif self.axis == 'Y':
            selected_objs.sort(key=lambda o: o.location.y)
            min_val = selected_objs[0].location.y
            max_val = selected_objs[-1].location.y
        else:
            selected_objs.sort(key=lambda o: o.location.z)
            min_val = selected_objs[0].location.z
            max_val = selected_objs[-1].location.z
        if min_val == max_val:
            self.report({'WARNING'}, "最小値と最大値が同じです。均等配置できません。")
            return {'CANCELLED'}
        count = len(selected_objs)
        step = (max_val - min_val) / (count - 1)
        for i, obj in enumerate(selected_objs):
            if self.axis == 'X':
                obj.location.x = min_val + step * i
            elif self.axis == 'Y':
                obj.location.y = min_val + step * i
            else:
                obj.location.z = min_val + step * i
        return {'FINISHED'}

# ---------- 2) Distribute by Fixed Interval ----------
class OBJECT_OT_distribute_fixed_interval(bpy.types.Operator):
    """基準オブジェクトから固定間隔で選択オブジェクトを配置（6方向）"""
    bl_idname = "object.distribute_fixed_interval"
    bl_label = "Distribute (Fixed Interval)"
    bl_options = {'REGISTER', 'UNDO'}

    direction: EnumProperty(
        name="Direction",
        description="配置する方向を選択",
        items=[
            ('+X', "+X", "最小Xオブジェクトを基準に+X方向へ配置"),
            ('-X', "-X", "最大Xオブジェクトを基準に-X方向へ配置"),
            ('+Y', "+Y", "最小Yオブジェクトを基準に+Y方向へ配置"),
            ('-Y', "-Y", "最大Yオブジェクトを基準に-Y方向へ配置"),
            ('+Z', "+Z", "最小Zオブジェクトを基準に+Z方向へ配置"),
            ('-Z', "-Z", "最大Zオブジェクトを基準に-Z方向へ配置"),
        ],
        default='+X'
    )

    distance: FloatProperty(
        name="Interval Distance",
        description="オブジェクト間の間隔",
        default=1.0,
        min=0.0
    )

    def execute(self, context):
        selected_objs = [obj for obj in context.selected_objects if obj.type in {'MESH', 'ARMATURE'}]
        if len(selected_objs) < 2:
            self.report({'WARNING'}, "2つ以上のオブジェクト（MESHまたはARMATURE）を選択してください。")
            return {'CANCELLED'}
        if self.direction == '+X':
            selected_objs.sort(key=lambda o: o.location.x)
            ref_obj_loc = selected_objs[0].location.copy()
            dir_vec = (1.0, 0.0, 0.0)
        elif self.direction == '-X':
            selected_objs.sort(key=lambda o: o.location.x, reverse=True)
            ref_obj_loc = selected_objs[0].location.copy()
            dir_vec = (-1.0, 0.0, 0.0)
        elif self.direction == '+Y':
            selected_objs.sort(key=lambda o: o.location.y)
            ref_obj_loc = selected_objs[0].location.copy()
            dir_vec = (0.0, 1.0, 0.0)
        elif self.direction == '-Y':
            selected_objs.sort(key=lambda o: o.location.y, reverse=True)
            ref_obj_loc = selected_objs[0].location.copy()
            dir_vec = (0.0, -1.0, 0.0)
        elif self.direction == '+Z':
            selected_objs.sort(key=lambda o: o.location.z)
            ref_obj_loc = selected_objs[0].location.copy()
            dir_vec = (0.0, 0.0, 1.0)
        else:  # '-Z'
            selected_objs.sort(key=lambda o: o.location.z, reverse=True)
            ref_obj_loc = selected_objs[0].location.copy()
            dir_vec = (0.0, 0.0, -1.0)
        for i, obj in enumerate(selected_objs):
            dx = dir_vec[0] * self.distance * i
            dy = dir_vec[1] * self.distance * i
            dz = dir_vec[2] * self.distance * i
            obj.location = (
                ref_obj_loc[0] + dx,
                ref_obj_loc[1] + dy,
                ref_obj_loc[2] + dz
            )
        return {'FINISHED'}

# ========================================================
# 6. UIパネル（全機能をひとつのパネルに統合）
# ========================================================

class VIEW3D_PT_voxel_adjust_tools(bpy.types.Panel):
    bl_label = "Voxel adjust Tools"
    bl_idname = "VIEW3D_PT_voxel_adjust_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Voxel adjust"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # --- OBJインポート ---
        layout.label(text="OBJ Import:")
        layout.operator("object.import_obj_one_click", text="Import OBJ")
        layout.separator()

        # --- Merge By Distance ---
        layout.label(text="Merge By Distance:")
        op = layout.operator("object.merge_by_distance_operator", text="Merge By Distance")
        layout.prop(op, "merge_distance", text="Distance")
        layout.separator()

        # --- Set Pivot and Move to Curve Point (新機能) ---
        layout.label(text="Set Pivot and Move to Curve Point:")
        row = layout.row(align=True)
        row.operator("object.set_pivot_to_selection_center", text="Pivot to Sel. Center")
        row.operator("object.move_pivot_to_curve_point", text="Pivot to Curve Point")
        row.operator("object.move_selected_objects_to_origin", text="Move to Origin")
        layout.separator()

        # --- Pivot and Offset Tool ---
        layout.label(text="Pivot and Offset Tool:")
        layout.label(text="Pivot Mover:")
        row = layout.row(align=True)
        for axis in ['+X', '-X', '+Y', '-Y', '+Z', '-Z']:
            op = row.operator("object.pivot_mover", text=axis)
            op.axis = axis
        layout.separator()
        layout.label(text="Offset Controls:")
        layout.prop(scene, "move_origin_offset", text="Offset (m)")
        layout.label(text="Select Axis and Apply Offset:")
        row = layout.row(align=True)
        for axis in ['+X', '-X', '+Y', '-Y', '+Z', '-Z']:
            op = row.operator("object.set_axis_and_move", text=axis)
            op.axis = axis
        layout.separator()

        # --- Set Pivot (Extreme) ---
        layout.label(text="Set Pivot (Extreme):")
        row = layout.row(align=True)
        for axis in ['+X', '-X', '+Y', '-Y', '+Z', '-Z']:
            op = row.operator("object.set_pivot", text=axis)
            op.axis = axis
        layout.separator()

        # --- Vertex Group from Object Name ---
        layout.label(text="Vertex Group from Object Name:")
        layout.operator("object.create_vertex_groups", text="Create Vertex Groups")
        layout.separator()

        # --- Even Distribution ---
        layout.label(text="Even Distribution:")
        # ① Distribute Between Min and Max
        box1 = layout.box()
        box1.label(text="Distribute Between Min and Max", icon='ARROW_LEFTRIGHT')
        row = box1.row(align=True)
        row.operator("object.evenly_distribute", text="X").axis = 'X'
        row.operator("object.evenly_distribute", text="Y").axis = 'Y'
        row.operator("object.evenly_distribute", text="Z").axis = 'Z'
        # ② Distribute by Fixed Interval
        box2 = layout.box()
        box2.label(text="Distribute by Fixed Interval", icon='ARROW_LEFTRIGHT')
        box2.prop(context.scene, "fixed_distribution_distance", text="Interval")
        row = box2.row(align=True)
        row.operator("object.distribute_fixed_interval", text="+X").direction = '+X'
        row.operator("object.distribute_fixed_interval", text="-X").direction = '-X'
        row = box2.row(align=True)
        row.operator("object.distribute_fixed_interval", text="+Y").direction = '+Y'
        row.operator("object.distribute_fixed_interval", text="-Y").direction = '-Y'
        row = box2.row(align=True)
        row.operator("object.distribute_fixed_interval", text="+Z").direction = '+Z'
        row.operator("object.distribute_fixed_interval", text="-Z").direction = '-Z'

# ========================================================
# 7. プロパティの登録
# ========================================================

def register():
    # プロパティの登録
    bpy.types.Scene.move_origin_offset = FloatProperty(
        name="Offset",
        description="Pivotを移動する距離",
        default=1.0,
        min=0.0
    )

    bpy.types.Scene.fixed_distribution_distance = FloatProperty(
        name="Distribution Distance",
        description="オブジェクト間の固定間隔",
        default=1.0,
        min=0.001
    )

    # クラスの登録
    bpy.utils.register_class(OBJECT_OT_import_obj)
    bpy.utils.register_class(OBJECT_OT_merge_by_distance_operator)
    bpy.utils.register_class(OBJECT_OT_SetPivotToSelectionCenter)
    bpy.utils.register_class(OBJECT_OT_MovePivotToCurvePoint)
    bpy.utils.register_class(OBJECT_OT_MoveSelectedObjectsToOrigin)
    bpy.utils.register_class(OBJECT_OT_set_pivot)
    bpy.utils.register_class(OBJECT_OT_CreateVertexGroups)
    bpy.utils.register_class(OBJECT_OT_PivotMover)
    bpy.utils.register_class(OBJECT_OT_SetAxisAndMove)
    bpy.utils.register_class(OBJECT_OT_evenly_distribute)
    bpy.utils.register_class(OBJECT_OT_distribute_fixed_interval)
    bpy.utils.register_class(VIEW3D_PT_voxel_adjust_tools)

def unregister():
    # プロパティの削除
    del bpy.types.Scene.move_origin_offset
    del bpy.types.Scene.fixed_distribution_distance

    # クラスの削除
    bpy.utils.unregister_class(VIEW3D_PT_voxel_adjust_tools)
    bpy.utils.unregister_class(OBJECT_OT_distribute_fixed_interval)
    bpy.utils.unregister_class(OBJECT_OT_evenly_distribute)
    bpy.utils.unregister_class(OBJECT_OT_SetAxisAndMove)
    bpy.utils.unregister_class(OBJECT_OT_PivotMover)
    bpy.utils.unregister_class(OBJECT_OT_CreateVertexGroups)
    bpy.utils.unregister_class(OBJECT_OT_set_pivot)
    bpy.utils.unregister_class(OBJECT_OT_MoveSelectedObjectsToOrigin)
    bpy.utils.unregister_class(OBJECT_OT_MovePivotToCurvePoint)
    bpy.utils.unregister_class(OBJECT_OT_SetPivotToSelectionCenter)
    bpy.utils.unregister_class(OBJECT_OT_merge_by_distance_operator)
    bpy.utils.unregister_class(OBJECT_OT_import_obj)

if __name__ == "__main__":
    register()

