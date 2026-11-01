using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading;
using Accessibility;

public static class ZaloQuoteCapture {
 [StructLayout(LayoutKind.Sequential)] struct RECT { public int L,T,R,B; }
 [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h,int n);
 [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h,out RECT r);
 [DllImport("user32.dll")] static extern bool PrintWindow(IntPtr h,IntPtr dc,uint flags);
 [DllImport("user32.dll")] static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] static extern void mouse_event(uint f,uint x,uint y,uint data,UIntPtr extra);
 delegate bool EnumChild(IntPtr h,IntPtr p);
 [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr h,EnumChild cb,IntPtr p);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h,System.Text.StringBuilder b,int n);
 [DllImport("oleacc.dll")] static extern int AccessibleObjectFromWindow(IntPtr h,uint id,ref Guid iid,[MarshalAs(UnmanagedType.Interface)] out IAccessible a);
 [DllImport("oleacc.dll")] static extern int AccessibleChildren(IAccessible a,int start,int count,[Out,MarshalAs(UnmanagedType.LPArray,SizeParamIndex=2)] object[] children,out int obtained);
 class Node { public IAccessible A;public int Child;public string Name;public Rectangle Box;public int Role;public int Depth;public Node Parent; }
 static string Norm(string s){return Regex.Replace((s??"").Normalize(),@"\s+"," ").Trim();}
 static List<Node> Read(IntPtr window){
  IntPtr renderer=IntPtr.Zero;
  EnumChild cb=delegate(IntPtr h,IntPtr p){var b=new System.Text.StringBuilder(256);GetClassName(h,b,256);if(b.ToString()=="Chrome_RenderWidgetHostHWND"){renderer=h;return false;}return true;};
  EnumChildWindows(window,cb,IntPtr.Zero);if(renderer==IntPtr.Zero)throw new Exception("Zalo renderer missing");
  Guid iid=new Guid("618736e0-3c3d-11cf-810c-00aa00389b71");IAccessible a;
  if(AccessibleObjectFromWindow(renderer,0xFFFFFFFC,ref iid,out a)!=0)throw new Exception("Zalo accessibility unavailable");
  var list=new List<Node>();Walk(a,0,null,0,list);return list;
 }
 static void Walk(IAccessible a,int child,Node parent,int depth,List<Node> list){
  if(depth>50||list.Count>20000)throw new Exception("Zalo tree limit");
  Node n;
  try{int x,y,w,h;a.accLocation(out x,out y,out w,out h,child);n=new Node{A=a,Child=child,Name=Norm(a.get_accName(child)),Box=new Rectangle(x,y,w,h),Role=Convert.ToInt32(a.get_accRole(child)),Depth=depth,Parent=parent};list.Add(n);}catch(COMException){return;}
  if(child!=0)return;
  int count=Math.Min(a.accChildCount,3000),got;var kids=new object[count];AccessibleChildren(a,0,count,kids,out got);
  for(int i=0;i<got;i++){if(kids[i] is IAccessible)Walk((IAccessible)kids[i],0,n,depth+1,list);else if(kids[i] is int)Walk(a,(int)kids[i],n,depth+1,list);}
 }
 static bool Under(Node n,Node parent){for(Node p=n;p!=null;p=p.Parent)if(p==parent)return true;return false;}
 static Node Header(List<Node> nodes,string group){
  var found=nodes.FindAll(n=>n.Depth<11&&n.Name.Contains(Norm(group))&&n.Name.Contains("thành viên")&&n.Box.Width>400);
  if(found.Count!=1)return null;return found[0];
 }
 static void Click(Node n){if(n.Box.Width<1||n.Box.Height<1)throw new Exception("Group not visible");SetCursorPos(n.Box.Left+n.Box.Width/2,n.Box.Top+n.Box.Height/2);mouse_event(2,0,0,0,UIntPtr.Zero);mouse_event(4,0,0,0,UIntPtr.Zero);}
 public static string Capture(string group,string body,string sender,string quoteSender,string clock,string date,string output){
  SetProcessDPIAware();var windows=new List<Process>();foreach(var p in Process.GetProcessesByName("Zalo"))if(p.MainWindowHandle!=IntPtr.Zero&&p.MainWindowTitle=="Zalo")windows.Add(p);
  if(windows.Count!=1)throw new Exception("Expected one Zalo window");IntPtr h=windows[0].MainWindowHandle;
  ShowWindow(h,9);SetForegroundWindow(h);Thread.Sleep(300);var nodes=Read(h);var head=Header(nodes,group);
  if(head==null){
   var rows=nodes.FindAll(n=>n.Name==Norm(group)&&n.Box.Width>0&&n.Box.Height>0);
   if(rows.Count==0){var search=nodes.FindAll(n=>n.Name=="Tìm kiếm"&&n.Role==42);if(search.Count!=1)throw new Exception("Search field not unique");search[0].A.set_accValue(search[0].Child,group);Thread.Sleep(800);nodes=Read(h);rows=nodes.FindAll(n=>n.Name==Norm(group)&&n.Box.Width>0&&n.Box.Height>0);}
   if(rows.Count!=1)throw new Exception("Group selection ambiguous");Click(rows[0]);Thread.Sleep(800);nodes=Read(h);head=Header(nodes,group);
  }
  if(head==null)throw new Exception("Active group mismatch");
  string target=Norm(body);if(target.Length<20)throw new Exception("Message text too short");
  var hits=nodes.FindAll(n=>n.Name.EndsWith(target,StringComparison.Ordinal)&&Under(n,head)&&n.Box.Width>0&&n.Box.Height>0);
  if(hits.Count!=1)throw new Exception("Exact current message not visible or ambiguous");
  string day="";foreach(var n in nodes){if(n==hits[0])break;if(Under(n,head)&&(n.Name=="Hôm nay"||n.Name=="Hôm qua"||Regex.IsMatch(n.Name,@"^(?:(?:T[2-7]|CN) )?(?:\d{1,2}:\d{2} )?\d{2}/\d{2}/\d{4}$")))day=n.Name;}
  var now=TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow,TimeZoneInfo.FindSystemTimeZoneById("SE Asia Standard Time"));
  if(!(day.EndsWith(date,StringComparison.Ordinal)||(day=="Hôm nay"&&date==now.ToString("dd/MM/yyyy"))||(day=="Hôm qua"&&date==now.AddDays(-1).ToString("dd/MM/yyyy"))))throw new Exception("Message date mismatch");
  Node bubble=null;
  for(Node p=hits[0].Parent;p!=null&&p!=head;p=p.Parent){
   bool author=false,quote=false,time=false,picture=false;
   foreach(var n in nodes)if(Under(n,p)){if(n.Name==Norm(sender))author=true;if(n.Name==Norm(quoteSender))quote=true;if(n.Name==clock)time=true;if(n.Role==40)picture=true;}
   if(author&&quote&&time&&picture){bubble=p;break;}
  }
  if(bubble==null)throw new Exception("Quoted image, author or time not matched in the message");
  RECT r;GetWindowRect(h,out r);Rectangle wr=new Rectangle(r.L,r.T,r.R-r.L,r.B-r.T);
  if(!wr.Contains(hits[0].Box))throw new Exception("Message not fully visible: "+wr+" vs "+hits[0].Box);
  using(var bmp=new Bitmap(wr.Width,wr.Height)){
   using(var g=Graphics.FromImage(bmp)){IntPtr dc=g.GetHdc();try{if(!PrintWindow(h,dc,2))throw new Exception("PrintWindow failed");}finally{g.ReleaseHdc(dc);}}
   var crop=Rectangle.Intersect(new Rectangle(head.Box.Left-wr.Left,head.Box.Top-wr.Top,head.Box.Width,head.Box.Height),new Rectangle(0,0,bmp.Width,bmp.Height));
   if(crop.Width<400||crop.Height<300)throw new Exception("Chat bounds invalid");
   var colors=new HashSet<int>();for(int x=0;x<bmp.Width;x+=31)for(int y=0;y<bmp.Height;y+=31)colors.Add(bmp.GetPixel(x,y).ToArgb());if(colors.Count<5)throw new Exception("Blank screenshot");
   var after=Read(h);if(Header(after,group)==null||after.FindAll(n=>n.Name.EndsWith(target,StringComparison.Ordinal)&&n.Box.Width>0).Count!=1)throw new Exception("Chat changed during capture");
   using(var result=bmp.Clone(crop,PixelFormat.Format24bppRgb))result.Save(output,ImageFormat.Png);
  }
  return "verified_group_text_sender_time_quote";
 }
}
