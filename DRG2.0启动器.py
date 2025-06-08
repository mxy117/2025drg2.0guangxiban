import tkinter as tk
from tkinter import filedialog, messagebox
from GroupProxy import GroupProxy


def select_and_process():
    # 初始化Tkinter主窗口并隐藏
    root = tk.Tk()
    root.withdraw()

    # 弹出文件选择对话框
    filename = filedialog.askopenfilename(
        title="请选择CSV文件",
        filetypes=[("CSV 文件", "*.csv")]
    )

    if not filename:
        messagebox.showerror("错误", "未选择任何文件")
        return

    try:
        # 初始化分组处理器
        proxy = GroupProxy()

        # 定义字段顺序（与 MedicalRecord 类属性一致）
        cols = ["Index", "gender", "age", "ageDay", "weight", "dept",
                "inHospitalTime", "leavingType", "zdList", "ssList", "remark"]

        # 调用 group_csv 方法进行处理
        output_file = proxy.group_csv(filename, cols)

        # 提示用户完成
        messagebox.showinfo("成功", f"处理完成，结果已保存至：\n{output_file}")

    except Exception as e:
        messagebox.showerror("运行错误", str(e))


if __name__ == "__main__":
    select_and_process()
