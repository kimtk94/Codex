module.exports=async function handler(req,res){
  res.setHeader('Cache-Control','no-store');
  res.status(200).json({status:'ok',app:'kalman-shadow-readonly',trade_execution:false,read_only:true});
};
