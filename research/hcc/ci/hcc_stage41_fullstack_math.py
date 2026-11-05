"""Stage41 conservative 3D DICOM source stack image comparison math."""
import numpy as np
MODES=[(t,a,b) for t in (False,True) for a in (False,True) for b in (False,True)]
def orient(a,m):
    t,f0,f1=m
    a=a.T if t else a
    if f0:a=a[::-1,:]
    if f1:a=a[:,::-1]
    return a
def best_map(vol,stack,grid=48):
    h,w,n=vol.shape
    assert n==len(stack)
    iy=np.linspace(0,h-1,grid).astype(int)
    ix=np.linspace(0,w-1,grid).astype(int)
    ref=vol[iy[:,None],ix[None,:],:].reshape(grid*grid,n).T.astype(np.float64)
    ref-=ref.mean(axis=1,keepdims=True)
    norm=np.linalg.norm(ref,axis=1)
    if np.min(norm)<1e-9:raise ValueError("Constant NIfTI slice")
    ref/=norm[:,None]
    best=None
    for mode in MODES:
        samples=[]
        for item in stack:
            arr=orient(item["pixels"],mode)
            if arr.shape!=(h,w):break
            v=arr[iy[:,None],ix[None,:]].astype(np.float64).ravel()
            v-=v.mean()
            den=np.linalg.norm(v)
            if den<1e-9:break
            samples.append(v/den)
        if len(samples)!=n:continue
        mat=np.vstack(samples)
        for reverse in (False,True):
            dst=ref[::-1] if reverse else ref
            cc=np.clip(np.einsum("ij,ij->i",mat,dst),-1,1)
            criterion=(float(cc.mean()),float(cc.min()))
            if best is None or criterion>best["criterion"]:
                best=dict(mode=mode,reverse=reverse,criterion=criterion)
    if best is None:raise ValueError("No consistent source image 3D axes")
    return best
def fullres_compare(vol,stack,best):
    n=len(stack);rows=[]
    for i,item in enumerate(stack):
        z=n-1-i if best["reverse"] else i
        src=orient(item["pixels"],best["mode"]).astype(np.float64)
        dst=vol[:,:,z].astype(np.float64)
        if src.shape!=dst.shape:raise ValueError("Source image pixel shape mismatch")
        src-=src.mean()
        dst-=dst.mean()
        xx=float(np.sum(src*src));yy=float(np.sum(dst*dst))
        if xx<1e-9 or yy<1e-9:
            corr=rmse=None
        else:
            xy=float(np.sum(src*dst))
            corr=float(np.clip(xy/np.sqrt(xx*yy),-1,1))
            rmse=float(np.linalg.norm(dst-(xy/xx)*src)/np.sqrt(yy))
        rows.append(dict(dicom_index=i,pv_z=z,pearson=corr,
                         normalized_linear_fit_rmse=rmse,
                         SOPInstanceUID=item["sop"],original_member_sha256=item["sha256"]))
    return rows
def coordinate_errors(vol,affine,stack,best):
    conversion=np.diag([-1.,-1.,1.]);n=len(stack);errors=[]
    for k in sorted({0,n//2,n-1}):
        item=stack[k];h,w=item["pixels"].shape
        ri=np.broadcast_to(np.arange(h)[:,None],(h,w))
        ci=np.broadcast_to(np.arange(w)[None,:],(h,w))
        row=orient(ri,best["mode"]);col=orient(ci,best["mode"])
        iop=item["iop"];sp=item["spacing"];p=item["ipp"]
        z=n-1-k if best["reverse"] else k
        for x,y in ((0,0),(vol.shape[0]//2,vol.shape[1]//2),(vol.shape[0]-1,vol.shape[1]-1)):
            lps=p+float(col[x,y])*sp[1]*iop[:3]+float(row[x,y])*sp[0]*iop[3:]
            actual=conversion@lps
            expected=(affine@np.array([x,y,z,1.0]))[:3]
            errors.append(float(np.linalg.norm(actual-expected)))
    return errors
def offline_test():
    yy,xx,zz=np.mgrid[:18,:13,:8]
    pv=(yy*2+xx*5+zz*(yy*xx+3)).astype(np.float32)
    stack=[dict(pixels=pv[:,:,z].T[::-1,:],sop=str(z),sha256="synthetic") for z in range(8)]
    best=best_map(pv,stack)
    rows=fullres_compare(pv,stack,best)
    assert len(rows)==8 and min(r["pearson"] for r in rows)>.9999999
    assert max(r["normalized_linear_fit_rmse"] for r in rows)<1e-6
    assert best["criterion"][1]>.99999
    print("HCC_STAGE41_3D_ORIENTATION_AND_FULLRES_SYNTHETIC_TEST_PASS")
if __name__=="__main__":offline_test()
